"""Pantry: a small storefront with planted defects for Argus demos."""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


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


ALL_BUGS = ["SH-01", "SH-02", "SH-03", "SH-04", "SH-05", "SH-06", "SH-07", "SH-08"]
BUGS = BugRegistry(os.getenv("BUGS"))
LOCK = threading.RLock()
PRODUCTS = [
    {"slug": "oat-milk", "name": "Oat Milk", "price": 4.50, "color": "#e9d8b4"},
    {"slug": "sourdough-loaf", "name": "Sourdough Loaf", "price": 6.25, "color": "#c99a5b"},
    {"slug": "cold-brew", "name": "Cold Brew Coffee", "price": 8.00, "color": "#5b3a29"},
    {"slug": "honey-jar", "name": "Wildflower Honey", "price": 11.75, "color": "#f2b134"},
]
COUPONS = {"SAVE10": 10}
carts: dict[str, dict[str, int]] = {}
saved_baskets: dict[str, int] = {}
orders: list[dict] = []


def reset_state() -> None:
    with LOCK:
        carts.clear()
        saved_baskets.clear()
        orders.clear()


def cart_view(sid: str) -> dict:
    with LOCK:
        cart = dict(carts.get(sid, {}))
    items = []
    for product in PRODUCTS:
        qty = cart.get(product["slug"], 0)
        if qty:
            items.append({"slug": product["slug"], "name": product["name"], "price": product["price"], "qty": qty})
    if BUGS.bug("SH-02"):
        # Planted: the total ignores quantity, so repeat adds are undercharged.
        total = sum(item["price"] for item in items)
    else:
        total = sum(item["price"] * item["qty"] for item in items)
    return {"items": items, "count": sum(item["qty"] for item in items), "total": round(total, 2)}


def product_svg(product: dict) -> bytes:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160" viewBox="0 0 240 160">'
        f'<rect width="240" height="160" rx="12" fill="{product["color"]}"/>'
        '<circle cx="120" cy="80" r="38" fill="#ffffff55"/>'
        f'<text x="120" y="148" font-family="sans-serif" font-size="14" text-anchor="middle" fill="#1d2420">{product["name"]}</text>'
        "</svg>"
    ).encode()


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title} — Pantry</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:48px auto;padding:0 20px;color:#1d2420}}a{{color:#2f6f4f}}</style>
</head><body><p><a href="/">← Back to Pantry</a></p><h1>{title}</h1><p>{body}</p></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "PantryDemo/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.log_date_time_string()} {fmt % args}")

    def _sid(self) -> tuple[str, bool]:
        match = re.search(r"(?:^|;\s*)pantry_sid=([a-f0-9]+)", self.headers.get("Cookie", ""))
        return (match.group(1), False) if match else (uuid.uuid4().hex, True)

    def _send(self, status: int, body: object = None, content_type: str = "application/json; charset=utf-8") -> None:
        payload = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        sid, fresh = self._sid()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if fresh:
            # Each browser context gets its own cart so parallel tests never collide.
            self.send_header("Set-Cookie", f"pantry_sid={sid}; Path=/; SameSite=Lax")
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
        path = urlparse(self.path).path
        if path == "/":
            html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
            html = html.replace("/*BUGS*/[]", json.dumps(BUGS.enabled()))
            self._send(200, html.encode(), "text/html; charset=utf-8")
        elif path == "/deals" and not BUGS.bug("SH-07"):
            self._page(200, "Today's deals", "Use code SAVE10 at checkout for 10% off your basket.")
        elif path == "/help":
            self._page(200, "Help", "Orders ship within two working days. Contact help@pantry.test with questions.")
        elif path == "/favicon.ico":
            self._send(204)
        elif match := re.fullmatch(r"/static/img/([a-z-]+)\.svg", path):
            product = next((item for item in PRODUCTS if item["slug"] == match.group(1)), None)
            if product is None:
                self._send(404, {"error": "Image not found"})
            else:
                self._send(200, product_svg(product), "image/svg+xml")
        elif path == "/api/products":
            products = []
            for product in PRODUCTS:
                image = f"/static/img/{product['slug']}.svg"
                if BUGS.bug("SH-01") and product["slug"] == "sourdough-loaf":
                    image = "/static/img/sourdough-loaf.png"  # Planted: asset was never uploaded.
                products.append({**{k: product[k] for k in ("slug", "name", "price")}, "image": image})
            self._send(200, {"products": products})
        elif path == "/api/cart":
            self._send(200, cart_view(self._sid()[0]))
        elif path == "/api/health":
            self._send(200, {"ok": True, "bugs": BUGS.enabled()})
        else:
            self._page(404, "Page not found", "We couldn't find that page.")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        sid = self._sid()[0]
        data = self._body()
        if path == "/__test/reset":
            reset_state()
            self._send(204)
        elif path == "/api/cart":
            slug = str(data.get("slug", ""))
            if not any(product["slug"] == slug for product in PRODUCTS):
                self._send(404, {"error": "Unknown product"})
                return
            with LOCK:
                cart = carts.setdefault(sid, {})
                cart[slug] = cart.get(slug, 0) + 1
            self._send(200, cart_view(sid))
        elif path == "/api/saved-baskets":
            with LOCK:
                saved_baskets[sid] = saved_baskets.get(sid, 0) + 1
                saved = saved_baskets[sid]
            self._send(201, {"saved": saved})
        elif path == "/api/coupon":
            code = str(data.get("code", "")).strip().upper()
            if code in COUPONS:
                self._send(200, {"valid": True, "discount": {"percent": COUPONS[code]}})
            else:
                self._send(200, {"valid": False, "message": "That coupon code isn't recognised."})
        elif path == "/api/orders":
            name = str(data.get("name", "")).strip()
            email = str(data.get("email", "")).strip()
            if not name or "@" not in email:
                self._send(400, {"error": "Enter your name and a valid email address."})
                return
            if BUGS.bug("SH-03"):
                # Planted: the inventory call fails, but the UI still reports success.
                self._send(500, {"error": "Inventory service unavailable"})
                return
            with LOCK:
                order = {"id": len(orders) + 1001, "name": name, "email": email, "cart": cart_view(sid)}
                orders.append(order)
                carts.pop(sid, None)
            self._send(201, {"order": {"id": order["id"]}})
        else:
            self._send(404, {"error": "Not found"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3101"))
    print(f"Pantry demo listening on 0.0.0.0:{port}; enabled bugs: {BUGS.enabled() or 'none'}")
    # The tester opens many browser contexts at once; the stdlib default
    # backlog of 5 refuses connections under that burst.
    ThreadingHTTPServer.request_queue_size = 128
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
