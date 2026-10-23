"""Main text of an HTML page (ported from web-search-mcp src/enhanced-content-extractor.ts, parseContent).

Same approach: drop non-content tags and page chrome (nav, header, footer, ads, cookie banners…), then take
the first substantial main-content element (article, main, .content…), else the body. Differences:
- Ad/tracking elements are matched on whole class/id words ("ad", "ads", "advert…"), not substrings:
  the original's [class*="ad"] also removed "header", "readme", "loading", "shadow"… and with them real content.
- Words like "terms", "conditions", "privacy" and "legal" are kept: the original deleted them from the text,
  which wipes exactly the retention/terms facts the agent's research looks for.
- Line breaks between blocks are kept, so sentences can be found per paragraph.
"""
import re

from bs4 import BeautifulSoup

REMOVE_TAGS = [
    "script", "style", "noscript", "iframe", "img", "video", "audio", "canvas", "svg", "object", "embed", "applet",
    "form", "input", "textarea", "select", "button", "label", "fieldset", "legend", "optgroup", "option",
    "nav", "header", "footer", "aside", "picture", "source", "figure", "figcaption",
]
REMOVE_SELECTORS = (
    ".nav, .header, .footer, .sidebar, .menu, .breadcrumb, .advertisement, .advertisement-container, "
    ".social-share, .share-buttons, .comments, .comment-section, .related-posts, .recommendations, "
    ".newsletter-signup, .cookie-notice, .privacy-notice, .terms-notice, .author-info, .publish-date, "
    ".navigation, .pagination, .search-box, .search-form, .login-form, .signup-form, .newsletter, .popup, "
    ".modal, .overlay, .tooltip, .toolbar, .ribbon, .banner, .promo, .sponsored, .affiliate, .gallery, "
    ".slideshow, .carousel, [style*='background-image']"
)
# Whole words in class/id attributes that mark page chrome, ads and tracking.
NOISE_WORDS = {
    "ad", "ads", "advert", "advertisement", "adsbygoogle", "tracking", "analytics", "pixel", "beacon", "sponsored",
    "affiliate", "promo", "banner", "popup", "modal", "overlay", "tooltip", "toolbar", "ribbon", "cookie", "cookies",
    "consent", "gdpr",
}
NOISE_ID_WORDS = NOISE_WORDS | {"sidebar", "navigation", "menu", "footer", "header"}
CONTENT_SELECTORS = [
    "article", "main", "[role='main']", ".content", ".post-content", ".entry-content", ".article-content",
    ".story-content", ".news-content", ".main-content", ".page-content", ".text-content", ".body-content",
    ".copy", ".text", ".body",
]
_IMAGE_URL_RE = re.compile(r"https?://\S+\.(?:jpe?g|png|gif|webp|svg|ico|bmp|tiff)(?:\?\S*)?", re.I)
_DATA_URL_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")


def _words(value) -> set[str]:
    text = " ".join(value) if isinstance(value, list) else str(value or "")
    return {w for w in re.split(r"[\s_\-]+", text.lower()) if w}


def html_to_text(html: str, max_chars: int = 500_000) -> tuple[str, str]:
    """(title, main text) of an HTML page; text keeps one line per block, whitespace collapsed."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(REMOVE_TAGS):
        tag.decompose()
    for el in soup.select(REMOVE_SELECTORS):
        el.decompose()
    for el in soup.find_all(True):
        if el.decomposed or el.attrs is None:
            continue
        if _words(el.get("class")) & NOISE_WORDS or _words(el.get("id")) & NOISE_ID_WORDS:
            el.decompose()

    text = ""
    for selector in CONTENT_SELECTORS:
        el = soup.select_one(selector)
        if el is not None:
            text = el.get_text("\n", strip=True)
            if len(text) > 100:
                break
    if len(text) < 100 and soup.body is not None:
        text = soup.body.get_text("\n", strip=True)
    return title, clean_text(text, max_chars)


def clean_text(text: str, max_chars: int = 500_000) -> str:
    text = _DATA_URL_RE.sub("", text)
    text = _IMAGE_URL_RE.sub("", text)
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)[:max_chars]


def preview(text: str, max_chars: int = 500) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= max_chars else flat[:max_chars] + "..."
