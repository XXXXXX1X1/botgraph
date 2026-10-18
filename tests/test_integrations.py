"""Адаптеры send_chart для aiogram и python-telegram-bot — на подставном боте, без сети."""

import asyncio
import io

import pytest

from botgraph import BotGraphValidationError

aiogram_adapter = pytest.importorskip("botgraph.integrations.aiogram")
ptb_adapter = pytest.importorskip("botgraph.integrations.ptb")
from aiogram.types import BufferedInputFile  # noqa: E402 — только после importorskip

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DATA = {"title": "Кошки <и> собаки", "labels": ["Кошки", "Собаки"], "values": [12, 8]}


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_photo(self, **kwargs):
        self.calls.append(("photo", kwargs))
        return "sent"

    async def send_message(self, **kwargs):
        self.calls.append(("message", kwargs))
        return "sent"


def _send(adapter, *args, **kwargs):
    bot = FakeBot()
    result = asyncio.run(adapter.send_chart(bot, 42, *args, **kwargs))
    assert result == "sent"
    return bot.calls


def test_aiogram_sends_png_as_buffered_file():
    [(method, kwargs)] = _send(aiogram_adapter, DATA, "bar", "dark", caption="За день")
    assert method == "photo" and kwargs["chat_id"] == 42 and kwargs["caption"] == "За день"
    assert isinstance(kwargs["photo"], BufferedInputFile)
    assert kwargs["photo"].data.startswith(PNG_SIGNATURE)


def test_ptb_sends_png_file_object():
    [(method, kwargs)] = _send(ptb_adapter, DATA, kind="line")
    assert method == "photo" and kwargs["caption"] is None
    assert isinstance(kwargs["photo"], io.BytesIO)
    assert kwargs["photo"].read(8) == PNG_SIGNATURE


@pytest.mark.parametrize("adapter", [aiogram_adapter, ptb_adapter])
def test_as_text_sends_escaped_pre(adapter):
    [(method, kwargs)] = _send(adapter, DATA, as_text=True, caption="Итог <b>")
    assert method == "message" and kwargs["parse_mode"] == "HTML"
    assert kwargs["text"].startswith("Итог &lt;b&gt;\n<pre>Кошки &lt;и&gt; собаки\n")
    assert kwargs["text"].endswith("</pre>")


@pytest.mark.parametrize("adapter", [aiogram_adapter, ptb_adapter])
@pytest.mark.parametrize("as_text", [False, True])
def test_bad_data_raises_and_sends_nothing(adapter, as_text):
    bot = FakeBot()
    with pytest.raises(BotGraphValidationError):
        asyncio.run(adapter.send_chart(bot, 42, {"labels": ["a"], "values": ["x"]}, as_text=as_text))
    assert bot.calls == []
