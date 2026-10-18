"""Веб-демо: страница «JSON → график» и HTTP API поверх render_png / render_text. Только стандартная библиотека.

    python3 examples/web.py            # http://127.0.0.1:8000
    HOST=0.0.0.0 PORT=8000 python3 examples/web.py

API:
    POST /api/png?kind=bar&theme=light   тело — JSON с данными → image/png
    POST /api/text?kind=bar              тело — JSON с данными → text/plain
    GET  /api/examples                   готовые примеры {имя: {kind, data}}
Ошибка в данных — 400 и текст BotGraphValidationError: [КОД] Поле '…': что исправить.
"""

import html
import json
import logging
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from demo import EXAMPLES

from botgraph import BotGraphValidationError, __version__, render_png, render_text

MAX_BODY = 64 * 1024  # самый большой допустимый набор (календарь на 182 дня) занимает ~6 КБ
# Рисунок — 20–70 мс CPU; больше двух одновременно на маленьком сервере только удлиняют очередь.
_DRAWING = threading.BoundedSemaphore(2)
_QUEUE_WAIT_S = 10

_BOT_URL = os.environ.get("BOT_URL", "")  # ссылка на демо-бота, если он запущен: https://t.me/<имя>
_PAGE = (
    Path(__file__).with_name("web.html").read_text(encoding="utf-8")
    .replace("{{version}}", __version__)
    .replace("{{bot_link}}", f' Попробовать в Telegram: <a href="{html.escape(_BOT_URL)}">{html.escape(_BOT_URL)}</a>.'
             if _BOT_URL else "")
    .encode()
)
_EXAMPLES = json.dumps(
    {name: {"kind": kind, "data": data} for name, (kind, data) in EXAMPLES.items()}, ensure_ascii=False,
).encode()
_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' blob:; style-src 'unsafe-inline'; "
                               "script-src 'unsafe-inline'; frame-ancestors 'none'",
}

log = logging.getLogger("botgraph.web")


class Handler(BaseHTTPRequestHandler):
    server_version = f"botgraph/{__version__}"
    sys_version = ""
    timeout = 15  # медленный клиент не держит поток вечно

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", _PAGE)
        elif path == "/api/examples":
            self._send(HTTPStatus.OK, "application/json; charset=utf-8", _EXAMPLES)
        elif path == "/health":
            self._send(HTTPStatus.OK, "text/plain; charset=utf-8", b"ok")
        else:
            self._error(HTTPStatus.NOT_FOUND, "нет такой страницы")

    def do_POST(self):
        url = urlsplit(self.path)
        if url.path not in ("/api/png", "/api/text"):
            return self._error(HTTPStatus.NOT_FOUND, "нет такой страницы")
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit():
            return self._error(HTTPStatus.LENGTH_REQUIRED, "нужен заголовок Content-Length")
        if int(length) > MAX_BODY:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"данные больше {MAX_BODY // 1024} КБ")
        body = self.rfile.read(int(length))
        if not _DRAWING.acquire(timeout=_QUEUE_WAIT_S):
            return self._error(HTTPStatus.SERVICE_UNAVAILABLE, "сервер занят, попробуйте через минуту")
        try:
            kind = query.get("kind", "bar")
            if url.path == "/api/png":
                png = render_png(body, kind=kind, theme=query.get("theme", "light")).getvalue()
                self._send(HTTPStatus.OK, "image/png", png)
            else:
                self._send(HTTPStatus.OK, "text/plain; charset=utf-8", render_text(body, kind=kind).encode())
        except BotGraphValidationError as e:
            self._error(HTTPStatus.BAD_REQUEST, str(e))
        finally:
            _DRAWING.release()

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._send(status, "text/plain; charset=utf-8", message.encode())

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in _HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Путь без query и тела: в логе не оседают чужие данные.
        log.info("%s %s %s", self.command, urlsplit(self.path).path, args[1] if len(args) > 1 else "")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    log.info("botgraph %s: http://%s:%d", __version__, host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
