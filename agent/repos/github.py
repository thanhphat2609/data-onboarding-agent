"""Read files from a GitHub repository with the REST API (token: config.github_token())."""
import requests

API = "https://api.github.com"


def _get(url: str, token: str, raw: bool = False) -> requests.Response:
    headers = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=30)
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
    return _get(f"{API}/repos/{repo}/contents/{path}?ref={ref}", token, raw=True).text
