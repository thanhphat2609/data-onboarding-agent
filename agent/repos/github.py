"""Read files from a GitHub repository with the REST API (token: config.github_token())."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API = "https://api.github.com"

# Transient network errors (DNS hiccups, dropped connections, 502/503/504) are retried twice.
_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(max_retries=Retry(total=2, connect=2, read=2, backoff_factor=0.5, status_forcelist=(502, 503, 504), allowed_methods=("GET",))),
)


def _get(url: str, token: str, raw: bool = False) -> requests.Response:
    """A GET on the GitHub API with the token; raw=True asks for the file's raw content."""
    headers = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = _session.get(url, headers=headers, timeout=30)
    except requests.ConnectionError as exc:
        what = "DNS lookup of api.github.com failed" if "NameResolution" in str(exc) or "name resolution" in str(exc) else "connection failed"
        raise ConnectionError(
            f"Cannot reach api.github.com from the machine running the agent ({what}). "
            "This is a network/DNS problem there, not the token."
        ) from exc
    if resp.status_code == 401:
        raise PermissionError("GitHub token is invalid or expired.")
    if resp.status_code == 404:
        raise FileNotFoundError(f"Not found on GitHub (wrong repo/branch, or the token cannot read this repo): {url}")
    resp.raise_for_status()
    return resp


def tree(repo: str, ref: str, token: str) -> list[str]:
    """Paths of every file in the repo at `ref`. repo = "owner/name"."""
    data = _get(f"{API}/repos/{repo}/git/trees/{ref}?recursive=1", token).json()
    return [t["path"] for t in data.get("tree", []) if t.get("type") == "blob"]


def file(repo: str, ref: str, path: str, token: str) -> str:
    """The text of one file of a repo at a ref."""
    return _get(f"{API}/repos/{repo}/contents/{path}?ref={ref}", token, raw=True).text
