"""Веб-демо и демо-бот из examples/ — то, что развёрнуто на сервере."""

import asyncio
import http.client
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from botgraph import BotGraphValidationError, render_text, validate_payload

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
        ("/api/png", b'{"labels": ["a"], "values": ["x"]}', 400, "[INVALID_VALUE_TYPE] Поле 'values[0]'"),
        ("/api/png?theme=blue", DATA, 400, "[UNSUPPORTED_THEME]"),
        ("/api/text?kind=radar", DATA, 400, "[UNSUPPORTED_KIND]"),
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


bot = pytest.importorskip("telegram_bot_demo")  # нужен aiogram
from aiogram.exceptions import TelegramBadRequest  # noqa: E402 — только после importorskip


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


@pytest.mark.parametrize(("text", "code"), [("привет", "INVALID_JSON"), ('radar {"a": 1}', "UNSUPPORTED_KIND")])
def test_bot_rejects_unclear_request(text, code):
    with pytest.raises(BotGraphValidationError) as e:
        bot.parse_request(text)
    assert e.value.code == code


@pytest.mark.parametrize("name", EXAMPLES)
def test_bot_example_message_round_trips(name):
    # Кнопка «JSON» присылает пример сообщением; отправленный обратно, он должен рисоваться.
    message = bot.example_message(name)
    assert len(message) <= 4096  # лимит Telegram на сообщение
    kind, _, data = bot.parse_request(message)
    assert render_text(data, kind=kind) == render_text(EXAMPLES[name][1], kind=EXAMPLES[name][0])


@pytest.mark.parametrize("quotes", ["“”", "«»", "„“"])
def test_bot_reads_json_typed_on_phone(quotes):
    left, right = quotes
    text = f"pie {{{left}labels{right}: [{left}Кошки{right}, {left}Собаки{right}], {left}values{right}: [12, 8]}}"
    kind, _, data = bot.parse_request(text)
    assert validate_payload(data, kind).labels == ("Кошки", "Собаки")


def test_bot_keeps_guillemets_inside_valid_json():
    raw = '{"title": "Проект «Альфа»", "labels": ["a"], "values": [1]}'
    assert bot.parse_request(raw)[2] == raw


def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_bot_card_buttons_wrap_and_toggle_theme(theme):
    first, last = bot.NAMES[0], bot.NAMES[-1]
    other = "dark" if theme == "light" else "light"
    assert _callbacks(bot.card_keyboard(first, theme)) == [
        f"v:{first}:{other}", f"t:{first}", f"j:{first}", f"v:{last}:{theme}", "menu", f"v:{bot.NAMES[1]}:{theme}"]
    assert _callbacks(bot.card_keyboard(last, theme))[-1] == f"v:{first}:{theme}"


def test_bot_callback_data_fits_telegram_limit():
    markups = [bot.menu_keyboard()] + [bot.card_keyboard(n, t) for n in bot.NAMES for t in bot.THEMES]
    assert all(len(d.encode()) <= 64 for m in markups for d in _callbacks(m))


def test_bot_error_example_is_real_error():
    text = bot.error_example()
    assert "<b>LENGTH_MISMATCH</b> в поле <code>values</code>" in text and bot.ERROR_EXAMPLE in text


class FakeBot:
    """Записывает вызовы Bot API вместо отправки в Telegram."""

    def __init__(self, edit_error=None):
        self.calls, self.edit_error = [], edit_error

    def __getattr__(self, method):
        async def call(**kwargs):
            self.calls.append((method, kwargs))
            if method == "edit_message_media" and self.edit_error:
                raise self.edit_error
        return call


def _query(data, photo):
    async def answer(*args, **kwargs):
        pass
    message = SimpleNamespace(chat=SimpleNamespace(id=7), message_id=99, photo=photo)
    return SimpleNamespace(data=data, message=message, answer=answer)


def test_bot_buttons_under_photo_change_it_in_place():
    fake = FakeBot()
    asyncio.run(bot.show_example(_query("v:bar-compare:dark", photo=["фото"]), fake))
    [(method, kwargs)] = fake.calls
    assert method == "edit_message_media" and kwargs["message_id"] == 99
    assert kwargs["media"].caption == "Сравнение · 2 из 7"
    assert kwargs["media"].media.data.startswith(PNG_SIGNATURE)
    assert _callbacks(kwargs["reply_markup"])[0] == "v:bar-compare:light"


def test_bot_double_tap_sends_nothing_new():
    fake = FakeBot(TelegramBadRequest(method=None, message="Bad Request: message is not modified"))
    asyncio.run(bot.show_example(_query("v:pie:light", photo=["фото"]), fake))
    assert [m for m, _ in fake.calls] == ["edit_message_media"]


@pytest.mark.parametrize("edit_error", [None, TelegramBadRequest(method=None, message="Bad Request: message to edit not found")])
def test_bot_sends_new_card_when_cannot_edit(edit_error):
    fake = FakeBot(edit_error)
    photo = ["фото"] if edit_error else None  # без ошибки — нажатие в меню, там фото нет
    asyncio.run(bot.show_example(_query("v:line:light", photo=photo), fake))
    method, kwargs = fake.calls[-1]
    assert method == "send_photo" and kwargs["caption"] == "Линия · 3 из 7"
    assert _callbacks(kwargs["reply_markup"])[0] == "v:line:dark"


def test_bot_tour_shows_everything():
    fake, answers = FakeBot(), []

    async def answer(text, **kwargs):
        answers.append(text)
    message = SimpleNamespace(chat=SimpleNamespace(id=7), answer=answer)
    asyncio.run(bot.tour(message, fake))
    album = next(kwargs["media"] for method, kwargs in fake.calls if method == "send_media_group")
    assert [m.caption for m in album] == [bot._TITLES[n] for n in bot.NAMES]
    assert all(m.media.data.startswith(PNG_SIGNATURE) for m in album)
    assert any(method == "send_message" and "<pre>" in kwargs["text"] for method, kwargs in fake.calls)
    assert any("LENGTH_MISMATCH" in a for a in answers)
