"""Готовая отправка в Telegram: await send_chart(bot, chat_id, data).

    from botgraph.integrations.aiogram import send_chart   # pip install 'botgraph[aiogram]'
    from botgraph.integrations.ptb import send_chart       # pip install 'botgraph[ptb]'
"""

import asyncio
import html
import io

from ..png import render_png
from ..text import render_text


async def draw(data, kind: str, theme: str) -> io.BytesIO:
    """Рисование занимает десятки миллисекунд — в потоке, чтобы не держать цикл событий бота."""
    return await asyncio.to_thread(render_png, data, kind, theme)


def html_text(data, kind: str, caption: str | None) -> str:
    """Текстовый вариант в <pre>: колонки выровнены пробелами и нужен моноширинный шрифт."""
    body = f"<pre>{html.escape(render_text(data, kind))}</pre>"
    return f"{html.escape(caption)}\n{body}" if caption else body
