"""Tiny API-key proxy in front of Ollama, so a tunnelled Ollama (e.g. on Colab) isn't open to anyone.

Ollama itself has no auth. Run this next to Ollama and expose THIS port through the tunnel:

    OLLAMA_PROXY_KEY=<secret> python notebooks/ollama_auth_proxy.py --port 8000
    cloudflared tunnel --url http://localhost:8000

Clients must send `Authorization: Bearer <secret>` (the web UI's LLM settings "API key" field).
Standard library only; non-streaming requests only (that's all the agent uses).
"""
import argparse
import hmac
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.getenv("OLLAMA_UPSTREAM", "http://127.0.0.1:11434")
KEY = os.getenv("OLLAMA_PROXY_KEY", "")
ALLOWED_PATHS = ("/api/tags", "/api/chat", "/api/generate", "/api/show")


class Proxy(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        sent = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        return bool(KEY) and hmac.compare_digest(sent, KEY)

    def _reply(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _forward(self, method: str) -> None:
        if not self._authorized():
            return self._reply(401, b'{"error": "unauthorized"}')
        if not self.path.startswith(ALLOWED_PATHS):  # no pull/delete/push from outside
            return self._reply(403, b'{"error": "path not allowed"}')
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else None
        req = urllib.request.Request(UPSTREAM + self.path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                self._reply(resp.status, resp.read(), resp.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as err:
            self._reply(err.code, err.read())
        except urllib.error.URLError as err:
            self._reply(502, f'{{"error": "upstream unreachable: {err.reason}"}}'.encode())

    def do_GET(self):
        self._forward("GET")

    def do_POST(self):
        self._forward("POST")

    def log_message(self, fmt, *args):
        pass  # don't log request lines (they may contain prompts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not KEY:
        raise SystemExit("Set OLLAMA_PROXY_KEY first.")
    print(f"Proxy :{args.port} -> {UPSTREAM}")
    ThreadingHTTPServer(("0.0.0.0", args.port), Proxy).serve_forever()
