"""Extract request fields from user replies (rule-based + optional LLM) and validate the request."""
import re
import unicodedata
from datetime import date, datetime

from agent.state import FREQUENCIES, KNOWN_SOURCES, REQUIRED_FIELDS

DATE_RE = r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4}"
# Keywords are bilingual (Vietnamese + English) so users can answer in either language.
TODAY_WORDS = ["đến nay", "tới nay", "hiện tại", "hôm nay", "until now", "till now", "today", "now", "present"]
YES_WORDS = [
    "ok", "oke", "okay", "yes", "yep", "sure", "agree", "accept", "approve", "go ahead",
    "đồng ý", "chấp nhận", "được", "duyệt", "đúng",
]

SOURCE_ALIASES = {
    "ga4": ["ga4", "google analytics", "analytics 4"],
    "gsc": ["gsc", "search console"],
    "appsflyer": ["appsflyer", "apps flyer", "af"],
    "cm": ["cm", "cm360", "campaign manager"],
    "gam": ["gam", "ad manager", "dfp"],
    "dv360": ["dv360", "display & video", "display and video"],
    "dataforseo": ["dataforseo", "data for seo"],
}

FREQ_ALIASES = {
    "hourly": ["hourly", "every hour", "hằng giờ", "hàng giờ", "mỗi giờ", "theo giờ"],
    "daily": ["daily", "every day", "hằng ngày", "hàng ngày", "mỗi ngày", "ngày 1 lần"],
    "weekly": ["weekly", "every week", "hằng tuần", "hàng tuần", "mỗi tuần"],
    "one-off": ["one-off", "one off", "oneoff", "one time", "once", "một lần", "1 lần", "adhoc", "ad-hoc"],
}

FIELD_LABELS = {
    "dataset_description": ["dataset_description", "dataset", "mô tả", "description", "data cần", "nhu cầu", "mục đích"],
    "sources": ["sources", "source", "nguồn"],
    "date_range": ["date_range", "date range", "khoảng thời gian", "thời gian", "lịch sử", "range"],
    "eta": ["eta", "go live", "go-live", "golive", "deadline", "hạn"],
    "refresh_frequency": ["refresh_frequency", "refresh", "tần suất", "frequency"],
    "grain": ["grain", "mức chi tiết", "độ chi tiết", "granularity"],
    "consumers": ["consumers", "consumer", "used by", "users", "người dùng", "ai dùng", "dùng ở đâu", "sử dụng", "người sử dụng"],
}

LABEL_LINE_RE = re.compile(r"^\s*[-*•]?\s*(?P<label>[^:=\n]{1,40}?)\s*[:=]\s*(?P<value>.+)$")
NUMBERED_LINE_RE = re.compile(r"^\s*(?P<n>\d+)\s*[.)]\s*(?P<value>.+)$")


def norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().lower()


def to_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _contains_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", text) is not None


def find_sources(text: str) -> list[str]:
    t = norm(text)
    return [src for src, aliases in SOURCE_ALIASES.items() if any(_contains_word(t, a) for a in aliases)]


def find_frequency(text: str) -> str | None:
    t = norm(text)
    for freq, aliases in FREQ_ALIASES.items():
        if any(_contains_word(t, a) for a in aliases):
            return freq
    return None


def _date_tokens(text: str, today: date) -> list[date]:
    t = norm(text)
    pattern = "|".join([DATE_RE] + [re.escape(w) for w in TODAY_WORDS])
    out = []
    for m in re.finditer(pattern, t):
        tok = m.group(0)
        out.append(today if tok in TODAY_WORDS else to_date(tok))
    return [d for d in out if d]


def parse_range(text: str, today: date) -> dict | None:
    toks = _date_tokens(text, today)
    if len(toks) >= 2:
        return {"start": toks[0].isoformat(), "end": toks[1].isoformat()}
    return None


def parse_field(field: str, value: str, today: date):
    """Parse the value of one field. Returns None if it cannot be parsed."""
    value = value.strip()
    if not value:
        return None
    if field == "sources":
        found = find_sources(value)
        if found:
            return found
        raw = [norm(s) for s in re.split(r"[,;/]| và | and ", value) if s.strip()]
        return raw or None
    if field == "date_range":
        return parse_range(value, today)
    if field == "eta":
        toks = re.findall(DATE_RE, value)
        d = to_date(toks[0]) if toks else None
        return d.isoformat() if d else None
    if field == "refresh_frequency":
        return find_frequency(value)
    return value


def _label_to_field(label: str) -> str | None:
    label = norm(label)
    for field, aliases in FIELD_LABELS.items():
        if any(label == a or label.startswith(a) for a in aliases):
            return field
    return None


def rule_extract(text: str, asked_fields: list[str] | None, today: date, first_message: bool = False) -> dict:
    """Extract fields from text. asked_fields: fields just asked (used to map free-text answers)."""
    asked_fields = asked_fields or []
    found: dict = {}
    unlabeled_lines = []

    for line in text.splitlines():
        m = LABEL_LINE_RE.match(line)
        field = _label_to_field(m.group("label")) if m else None
        if field:
            val = parse_field(field, m.group("value"), today)
            if val:
                found[field] = val
            continue
        n = NUMBERED_LINE_RE.match(line)
        if n and asked_fields and 1 <= int(n.group("n")) <= len(asked_fields):
            field = asked_fields[int(n.group("n")) - 1]
            val = parse_field(field, n.group("value"), today)
            if val:
                found[field] = val
            continue
        if line.strip():
            unlabeled_lines.append(line)

    free = "\n".join(unlabeled_lines)
    if not free:
        return found

    # Explicit signals in free text
    if "sources" not in found and (srcs := find_sources(free)):
        found["sources"] = srcs
    if "refresh_frequency" not in found and (freq := find_frequency(free)):
        found["refresh_frequency"] = freq
    if "date_range" not in found:
        m = re.search(
            rf"(?:từ|from)\s+(?:ngày\s+)?({DATE_RE})\s*(?:đến|tới|to|until|till|through|-|–)\s*(?:ngày\s+)?({DATE_RE}|{'|'.join(TODAY_WORDS)}|nay)",
            norm(free),
        )
        if m:
            end = today if m.group(2) in TODAY_WORDS + ["nay"] else to_date(m.group(2))
            found["date_range"] = {"start": to_date(m.group(1)).isoformat(), "end": end.isoformat()}
    if "eta" not in found:
        m = re.search(rf"(?:eta|go[- ]?live|deadline|needed by|due|trước ngày|cần trước|hạn)\D{{0,20}}({DATE_RE})", norm(free))
        if m:
            found["eta"] = to_date(m.group(1)).isoformat()

    # Free-text answer to exactly one asked field
    pending = [f for f in asked_fields if f not in found]
    if len(asked_fields) == 1 and pending:
        val = parse_field(pending[0], free, today)
        if val:
            found[pending[0]] = val
    elif first_message and "dataset_description" not in found:
        found["dataset_description"] = free.strip()
    return found


def llm_extract(llm, system_prompt: str, request: dict, missing: list[str], text: str, today: date) -> dict:
    import json

    user = (
        f"Today: {today.isoformat()}\n"
        f"Current request: {json.dumps(request, ensure_ascii=False)}\n"
        f"Missing fields: {missing}\n"
        f"New user message:\n{text}"
    )
    raw = llm.complete_json(system_prompt, user) or {}
    out = {}
    for field in REQUIRED_FIELDS:
        val = raw.get(field)
        if val in (None, "", [], {}):
            continue
        if field == "sources":
            vals = val if isinstance(val, list) else [val]
            out[field] = find_sources(" ".join(map(str, vals))) or [norm(str(v)) for v in vals]
        elif field == "date_range" and isinstance(val, dict):
            s, e = to_date(val.get("start")), to_date(val.get("end"))
            if s and e:
                out[field] = {"start": s.isoformat(), "end": e.isoformat()}
        elif field == "eta":
            if d := to_date(val):
                out[field] = d.isoformat()
        elif field == "refresh_frequency":
            if f := find_frequency(str(val)):
                out[field] = f
        else:
            out[field] = str(val).strip()
    return out


def validate(request: dict, today: date) -> tuple[dict, dict[str, str]]:
    """Return (clean request, errors). Invalid fields are dropped so they get asked again."""
    clean = dict(request)
    errors: dict[str, str] = {}

    dr = clean.get("date_range")
    if dr:
        s, e = to_date(dr.get("start")), to_date(dr.get("end"))
        if not (s and e):
            errors["date_range"] = "Dates are not in a valid format."
        elif s > e:
            errors["date_range"] = f"Start date ({s}) is after end date ({e})."
        elif s > today:
            errors["date_range"] = f"Start date ({s}) is in the future."
    eta = clean.get("eta")
    if eta:
        d = to_date(eta)
        if not d:
            errors["eta"] = "ETA is not in a valid format."
        elif d <= today:
            errors["eta"] = f"ETA ({d}) must be after today ({today})."
    freq = clean.get("refresh_frequency")
    if freq and freq not in FREQUENCIES:
        errors["refresh_frequency"] = f"Refresh frequency must be one of {FREQUENCIES}."
    if "sources" in clean and not clean["sources"]:
        errors["sources"] = "At least one source is required."

    for field in errors:
        clean.pop(field, None)
    return clean, errors


def missing_fields(request: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if not request.get(f)]


def is_yes(text: str) -> bool:
    t = norm(text)
    return any(_contains_word(t, w) for w in YES_WORDS) and not re.search(r"\b(không|ko|no|not)\b", t)


def unknown_sources(sources: list[str]) -> list[str]:
    return [s for s in sources if s not in KNOWN_SOURCES]
