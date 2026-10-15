"""Веб-демо и демо-бот из examples/ — то, что развёрнуто на сервере."""

import http.client
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from botgraf import ChartError, render_text

sys.path.insert(0, str(Path(__file__).parents[1] / "examples"))
import web  # noqa: E402 — examples/ не пакет
from demo import EXAMPLES  # noqa: E402

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DATA = json.dumps({"labels": ["Кошки", "Собаки"], "values": [12, 8]}).encode()


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _request(url, body=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=10) as r:
            return r.status, r.headers["Content-Type"], r.read()
    except urllib.error.HTTPError as e:
        with e:
            return e.code, e.headers["Content-Type"], e.read()


def test_page_and_examples(base_url):
    status, ctype, body = _request(base_url + "/")
    assert status == 200 and ctype.startswith("text/html") and "БотГраф" in body.decode()
    status, _, body = _request(base_url + "/api/examples")
    assert json.loads(body).keys() == EXAMPLES.keys()


def test_png_and_text(base_url):
    status, ctype, body = _request(base_url + "/api/png?kind=pie&theme=dark", DATA)
    assert (status, ctype) == (200, "image/png") and body.startswith(PNG_SIGNATURE)
    status, _, body = _request(base_url + "/api/text", DATA)
    assert status == 200 and body.decode() == render_text(DATA)


@pytest.mark.parametrize(
    ("path", "body", "status", "message"),
    [
        ("/api/png", b'{"labels": ["a"], "values": ["x"]}', 400, "values[0] должно быть числом"),
        ("/api/png?theme=blue", DATA, 400, "theme должен быть"),
        ("/api/text?kind=radar", DATA, 400, "kind"),
        ("/api/nope", DATA, 404, "нет такой страницы"),
    ],
)
def test_errors_are_plain_text(base_url, path, body, status, message):
    got_status, ctype, got = _request(base_url + path, body)
    assert got_status == status and ctype.startswith("text/plain") and message in got.decode()


def test_too_large_body_rejected_before_reading(base_url):
    # Только заголовок: сервер должен отказать по Content-Length, не дожидаясь тела.
    conn = http.client.HTTPConnection(base_url.removeprefix("http://"), timeout=10)
    conn.putrequest("POST", "/api/png")
    conn.putheader("Content-Length", str(web.MAX_BODY + 1))
    conn.endheaders()
    response = conn.getresponse()
    assert response.status == 413 and "данные больше" in response.read().decode()
    conn.close()


bot = pytest.importorskip("bot")  # нужен aiogram


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', ("bar", "light", '{"a": 1}')),
        ('card dark {"a": 1}', ("card", "dark", '{"a": 1}')),
        ('/text LINE\n{"a": 1}', ("line", "light", '{"a": 1}')),
    ],
)
def test_bot_parses_kind_and_theme(text, expected):
    assert bot.parse_request(text) == expected


@pytest.mark.parametrize(("text", "message"), [("привет", "не вижу JSON"), ('radar {"a": 1}', "не понимаю «radar»")])
def test_bot_rejects_unclear_request(text, message):
    with pytest.raises(ChartError, match=message):
        bot.parse_request(text)


@pytest.mark.parametrize("name", EXAMPLES)
def test_bot_example_message_round_trips(name):
    # Кнопка «JSON» присылает пример сообщением; отправленный обратно, он должен рисоваться.
    message = bot.example_message(name)
    assert len(message) <= 4096  # лимит Telegram на сообщение
    kind, _, data = bot.parse_request(message)
    assert render_text(data, kind=kind) == render_text(EXAMPLES[name][1], kind=EXAMPLES[name][0])
