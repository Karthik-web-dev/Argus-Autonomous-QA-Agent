"""Small, resettable Conduit-inspired target for Argus development."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class BugRegistry:
    """Feature flags for deterministic planted defects; unset means clean."""

    def __init__(self, raw: str = "") -> None:
        self.flags = {flag.strip().upper() for flag in raw.split(",") if flag.strip()}

    def bug(self, bug_id: str) -> bool:
        return bug_id.upper() in self.flags or "DEMO" in self.flags


BUGS = BugRegistry(os.getenv("BUGS", ""))
LOCK = threading.RLock()
INITIAL_ARTICLES = [
    {"slug": "welcome-to-the-workbench", "title": "Welcome to the Workbench", "description": "A small place to share what you are building.", "body": "Welcome! This sample keeps its stories in memory so every run starts clean.", "tagList": ["welcome", "community"], "author": "Mira Chen", "favoritesCount": 4, "favorited": False},
    {"slug": "notes-from-a-quiet-garden", "title": "Notes from a Quiet Garden", "description": "A few lessons from tending a city balcony garden.", "body": "Start with the light you have, then choose plants that suit it.", "tagList": ["life", "ideas"], "author": "Jon Bell", "favoritesCount": 9, "favorited": False},
    {"slug": "shipping-small-changes", "title": "Shipping Small Changes", "description": "Why the smallest useful release is often the best one.", "body": "A small change is easier to review, understand, and improve.", "tagList": ["engineering", "workflow"], "author": "Asha Rao", "favoritesCount": 12, "favorited": False},
]
articles = json.loads(json.dumps(INITIAL_ARTICLES))
current_user: str | None = None


def reset_state() -> None:
    global articles, current_user
    with LOCK:
        articles = json.loads(json.dumps(INITIAL_ARTICLES))
        current_user = None


class Handler(BaseHTTPRequestHandler):
    server_version = "WorkbenchSample/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.log_date_time_string()} {fmt % args}")

    def _send(self, status: int, body: object = None, content_type: str = "application/json; charset=utf-8") -> None:
        payload = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, Path(__file__).with_name("index.html").read_bytes(), "text/html; charset=utf-8")
        elif parsed.path == "/api/stories":
            tag = parse_qs(parsed.query).get("topic", [""])[0].lower()
            with LOCK:
                result = [story for story in articles if not tag or tag in [t.lower() for t in story["tagList"]]]
                self._send(200, {"stories": result, "currentUser": current_user, "demoMode": bool(BUGS.flags)})
        elif parsed.path == "/api/topics":
            with LOCK:
                topics = sorted({tag for story in articles for tag in story["tagList"]})
            self._send(200, {"topics": topics})
        elif parsed.path == "/api/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        global current_user
        parsed = urlparse(self.path)
        if parsed.path == "/__test/reset":
            reset_state()
            self._send(204)
            return
        if parsed.path == "/api/auth/session":
            data = self._body()
            username = str(data.get("username", "")).strip()
            if not username:
                self._send(400, {"error": "Enter a display name."})
                return
            with LOCK:
                current_user = username
            self._send(200, {"user": {"username": username}})
            return
        if parsed.path == "/api/stories":
            data = self._body()
            title = str(data.get("title", "")).strip()
            if not title:
                self._send(400, {"error": "A story title is required."})
                return
            with LOCK:
                author = current_user or "Guest Writer"
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or f"story-{int(time.time())}"
                story = {"slug": slug, "title": title, "description": str(data.get("description", "")).strip(),
                         "body": str(data.get("body", "")).strip(),
                         "tagList": [x.strip() for x in str(data.get("topics", "")).split(",") if x.strip()],
                         "author": author, "favoritesCount": 0, "favorited": False}
                articles.insert(0, story)
            self._send(201, {"story": story})
            return
        match = re.fullmatch(r"/api/stories/([^/]+)/favorite", parsed.path)
        if match:
            with LOCK:
                story = next((item for item in articles if item["slug"] == match.group(1)), None)
                if story is None:
                    self._send(404, {"error": "Story not found"})
                    return
                story["favoritesCount"] += 2 if BUGS.bug("BUG-FN-01") else 1
                story["favorited"] = True
            if BUGS.bug("BUG-NW-03"):
                # Emulate a duplicate commit that can appear when a request is
                # submitted twice before the UI receives the first response.
                time.sleep(0.12)
                with LOCK:
                    story["favoritesCount"] += 1
            self._send(200, {"story": story})
            return
        self._send(404, {"error": "Not found"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3100"))
    print(f"Workbench sample listening on 0.0.0.0:{port}; enabled bug flags: {sorted(BUGS.flags)}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
