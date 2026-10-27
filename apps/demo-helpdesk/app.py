"""Relay: a small support-ticket portal with planted defects for Argus demos."""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class BugRegistry:
    """Feature flags for deterministic planted defects.

    Unset ``BUGS`` enables every defect (``DEMO``) because this app exists for
    demos; set ``BUGS=none`` for the clean build used by the mutation check.
    """

    def __init__(self, raw: str | None) -> None:
        raw = "DEMO" if raw is None else raw
        self.flags = {flag.strip().upper() for flag in raw.split(",") if flag.strip()} - {"NONE"}

    def bug(self, bug_id: str) -> bool:
        return bug_id.upper() in self.flags or "DEMO" in self.flags

    def enabled(self) -> list[str]:
        return [bug_id for bug_id in ALL_BUGS if self.bug(bug_id)]


ALL_BUGS = ["HD-01", "HD-02", "HD-03", "HD-04", "HD-05", "HD-06", "HD-07", "HD-08"]
BUGS = BugRegistry(os.getenv("BUGS"))
LOCK = threading.RLock()
PAGE_SIZE = 5
SUBJECTS = [
    "Cannot reset my password", "Invoice shows the wrong VAT number", "Export to CSV times out",
    "Two-factor code never arrives", "Team member cannot see shared board", "Dark mode resets on reload",
    "Webhook retries flood our endpoint", "Mobile app crashes on upload", "Need to change billing email",
    "SSO login loops back to start", "Search ignores archived tickets", "Request: keyboard shortcuts list",
]
INITIAL_TICKETS = [
    {"id": 2040 + i, "subject": subject, "status": ["Open", "Pending", "Solved"][i % 3],
     "priority": ["Normal", "High", "Low", "Urgent"][i % 4]}
    for i, subject in enumerate(SUBJECTS)
]
POPULAR = [
    {"title": "Resetting your password", "href": "/kb"},
    {"title": "Setting up two-factor authentication", "href": "/kb"},
    {"title": "Understanding your invoice", "href": "/kb"},
]
tickets: list[dict] = json.loads(json.dumps(INITIAL_TICKETS))
sessions: dict[str, str] = {}


def reset_state() -> None:
    global tickets
    with LOCK:
        tickets = json.loads(json.dumps(INITIAL_TICKETS))
        sessions.clear()


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title} — Relay Support</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:48px auto;padding:0 20px;color:#1f2433}}a{{color:#4b4fd8}}dt{{font-weight:600;margin-top:10px}}</style>
</head><body><p><a href="/">← Back to Relay Support</a></p><h1>{title}</h1>{body}</body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "RelayDemo/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.log_date_time_string()} {fmt % args}")

    def _session_user(self) -> str | None:
        match = re.search(r"(?:^|;\s*)relay_session=([a-f0-9]+)", self.headers.get("Cookie", ""))
        with LOCK:
            return sessions.get(match.group(1)) if match else None

    def _send(self, status: int, body: object = None, content_type: str = "application/json; charset=utf-8",
              cookie: str | None = None) -> None:
        payload = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _page(self, status: int, title: str, body: str) -> None:
        self._send(status, PAGE.format(title=title, body=body).encode(), "text/html; charset=utf-8")

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
            html = html.replace("/*BUGS*/[]", json.dumps(BUGS.enabled()))
            self._send(200, html.encode(), "text/html; charset=utf-8")
        elif path == "/account":
            user = self._session_user()
            if user is None and BUGS.bug("HD-07"):
                # Planted: the account page skips its session check and leaks a demo profile.
                user = "priya.nair@relay.test"
            if user is None:
                self._page(200, "Account", '<p>Please sign in to view your account.</p><p><a href="/">Go to sign in</a></p>')
            else:
                self._page(200, "Account", f"<dl><dt>Email</dt><dd>{user}</dd><dt>Plan</dt><dd>Business</dd>"
                                           "<dt>Billing contact</dt><dd>finance@relay.test</dd></dl>")
        elif path == "/kb":
            self._page(200, "Knowledge base", "<p>Guides for passwords, two-factor authentication and invoices.</p>")
        elif path == "/favicon.ico":
            self._send(204)
        elif path == "/api/tickets":
            query = parse_qs(parsed.query)
            q = query.get("q", [""])[0].strip().lower()
            try:
                page = max(1, int(query.get("page", ["1"])[0]))
            except ValueError:
                page = 1
            with LOCK:
                matched = [t for t in tickets if q in t["subject"].lower()]
            pages = max(1, -(-len(matched) // PAGE_SIZE))
            page = min(page, pages)
            start = (page - 1) * PAGE_SIZE
            self._send(200, {"tickets": matched[start:start + PAGE_SIZE], "page": page, "pages": pages, "total": len(matched)})
        elif path == "/api/kb/popular":
            if BUGS.bug("HD-08"):
                self._send(500, {"error": "Search index is rebuilding"})
            else:
                self._send(200, {"articles": POPULAR})
        elif path == "/api/health":
            self._send(200, {"ok": True, "bugs": BUGS.enabled()})
        else:
            self._page(404, "Page not found", "<p>We couldn't find that page.</p>")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        data = self._body()
        if path == "/__test/reset":
            reset_state()
            self._send(204)
        elif path == "/api/session":
            email = str(data.get("email", "")).strip()
            password = str(data.get("password", ""))
            if "@" not in email or len(password) < 8:
                self._send(400, {"error": "Enter your email and a password of at least 8 characters."})
                return
            token = uuid.uuid4().hex
            with LOCK:
                sessions[token] = email
            self._send(200, {"user": {"email": email}}, cookie=f"relay_session={token}; Path=/; HttpOnly; SameSite=Lax")
        elif path == "/api/tickets":
            subject = str(data.get("subject", "")).strip()
            email = str(data.get("email", "")).strip()
            if not subject or "@" not in email:
                self._send(400, {"error": "A subject and a valid email are required."})
                return
            if BUGS.bug("HD-04"):
                # Planted: ticket creation crashes server-side and the UI says nothing.
                self._send(500, {"error": "NoneType object has no attribute 'assign_agent'"})
                return
            with LOCK:
                ticket = {"id": max(t["id"] for t in tickets) + 1, "subject": subject, "status": "Open",
                          "priority": str(data.get("priority", "Normal"))}
                tickets.insert(0, ticket)
            self._send(201, {"ticket": ticket})
        else:
            self._send(404, {"error": "Not found"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3102"))
    print(f"Relay demo listening on 0.0.0.0:{port}; enabled bugs: {BUGS.enabled() or 'none'}")
    # The tester opens many browser contexts at once; the stdlib default
    # backlog of 5 refuses connections under that burst.
    ThreadingHTTPServer.request_queue_size = 128
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
