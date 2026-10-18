"""Демо-бот на aiogram 3: готовые примеры кнопками и график из своих данных.

    pip install '.[aiogram]'
    BOT_TOKEN=123:abc python3 examples/telegram_bot_demo.py

Свои данные — сообщением: необязательные вид и тема, затем JSON, например
    card dark {"metrics": [{"label": "Выручка", "value": 48200, "previous": 43000}]}
"""

import asyncio
import json
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from demo import EXAMPLES

from botgraph import BotGraphValidationError
from botgraph.integrations.aiogram import send_chart
from botgraph.schema import KINDS

THEMES = ("light", "dark")
_TITLES = {
    "bar": "Столбики", "bar-compare": "Сравнение", "line": "Линия", "line-compare": "Две линии",
    "pie": "Кольцо", "calendar": "Календарь", "card": "Карточка дня",
}
_HELP = (
    "Я рисую графики библиотекой БотГраф.\n\n"
    "Нажмите пример ниже — или пришлите свои данные: сначала вид и тема (необязательно), потом JSON.\n\n"
    'bar {"labels": ["Кошки", "Собаки"], "values": [12, 8]}\n'
    'line dark {"labels": ["пн", "вт", "ср"], "values": [3, 5, 4]}\n\n'
    f"Виды: {', '.join(KINDS)}. Темы: {', '.join(THEMES)}.\n"
    "/text — то же самое, но текстом вместо картинки.\n\n"
    "Ошибку в данных бот объяснит кодом и полем, например:\n"
    'bar {"labels": ["Кошки", "Собаки"], "values": [12]}'
)
# Бот на маленьком сервере: больше двух рисунков разом только удлиняют очередь.
_DRAWING = asyncio.Semaphore(2)

log = logging.getLogger("botgraph.bot")
dp = Dispatcher()


def parse_request(text: str) -> tuple[str, str, str]:
    """«[вид] [тема] {json}» → (вид, тема, json). Слова до JSON проверяются, чтобы опечатка не ушла молча."""
    head, brace, body = text.partition("{")
    if not brace:
        raise BotGraphValidationError("INVALID_JSON", "Не вижу JSON — данные должны начинаться с «{». Пример: /start", "data")
    kind, theme = "bar", "light"
    for word in head.split():
        word = word.lower()
        if word in KINDS:
            kind = word
        elif word in THEMES:
            theme = word
        elif word != "/text":
            raise BotGraphValidationError(
                "UNSUPPORTED_KIND", f"Не понимаю «{word}»: перед JSON можно указать вид ({', '.join(KINDS)}) и тему "
                f"({', '.join(THEMES)})", "kind",
            )
    return kind, theme, brace + body


def example_message(name: str) -> str:
    kind, data = EXAMPLES[name]
    return f"{kind} {json.dumps(data, ensure_ascii=False)}"


def _examples_keyboard() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=_TITLES[name], callback_data=f"ex:{name}:light") for name in EXAMPLES]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])


def _variants_keyboard(name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Тёмная тема", callback_data=f"ex:{name}:dark"),
        InlineKeyboardButton(text="Текстом", callback_data=f"ex:{name}:text"),
        InlineKeyboardButton(text="JSON", callback_data=f"ex:{name}:json"),
    ]])


async def _send(bot: Bot, chat_id: int, data, kind: str, theme: str, *,
                caption: str | None = None, as_text: bool = False) -> None:
    """Если Telegram не принял фото, тот же график уходит текстом — пользователь не остаётся без ответа."""
    if not as_text:
        try:
            await send_chart(bot, chat_id, data, kind, theme, caption=caption)
            return
        except TelegramAPIError as e:
            log.warning("фото не отправилось (%s) — отправляю текстом", e)
    await send_chart(bot, chat_id, data, kind, caption=caption, as_text=True)


@dp.message(CommandStart())
@dp.message(Command("help"))
async def start(message: Message) -> None:
    await message.answer(_HELP, reply_markup=_examples_keyboard())


@dp.callback_query(F.data.startswith("ex:"))
async def example(query: CallbackQuery, bot: Bot) -> None:
    _, name, mode = query.data.split(":")
    await query.answer()
    if name not in EXAMPLES:  # кнопка от старой версии бота
        return
    kind, data = EXAMPLES[name]
    chat_id = query.message.chat.id
    if mode == "json":
        # Это сообщение можно переслать боту обратно, поправив цифры, — так проще всего начать со своими данными.
        await bot.send_message(chat_id, example_message(name))
        return
    async with _DRAWING:
        await _send(bot, chat_id, data, kind, "dark" if mode == "dark" else "light",
                    caption=_TITLES[name], as_text=mode == "text")
    if mode == "light":
        await bot.send_message(chat_id, "Другие варианты:", reply_markup=_variants_keyboard(name))


@dp.message(F.text)
async def user_data(message: Message, bot: Bot) -> None:
    try:
        kind, theme, data = parse_request(message.text)
        async with _DRAWING:
            await _send(bot, message.chat.id, data, kind, theme, as_text=message.text.startswith("/text"))
    except BotGraphValidationError as e:
        await message.answer(f"Не получилось нарисовать: {e}")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bot = Bot(os.environ["BOT_TOKEN"])
    me = await bot.get_me()
    log.info("демо-бот @%s запущен", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
