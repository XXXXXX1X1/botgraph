"""Демо-бот на aiogram 3: всё управление кнопками, свои данные — сообщением.

    pip install '.[aiogram]'
    BOT_TOKEN=123:abc python3 examples/telegram_bot_demo.py

Свои данные — сообщением: необязательные вид и тема, затем JSON, например
    card dark {"metrics": [{"label": "Выручка", "value": 48200, "previous": 43000}]}
"""

import asyncio
import html
import json
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)
from demo import EXAMPLES

from botgraph import BotGraphValidationError, validate_payload
from botgraph.integrations import draw
from botgraph.integrations.aiogram import send_chart
from botgraph.schema import KINDS

THEMES = ("light", "dark")
NAMES = tuple(EXAMPLES)
_TITLES = {
    "bar": "Столбики", "bar-compare": "Сравнение", "line": "Линия", "line-compare": "Две линии",
    "pie": "Кольцо", "calendar": "Календарь", "card": "Карточка дня",
}
BTN_TOUR, BTN_EXAMPLES, BTN_OWN, BTN_ERROR = "🧪 Проверка за минуту", "📊 Примеры", "✍️ Свои данные", "⚠️ Пример ошибки"
# Постоянная клавиатура у поля ввода: меню всегда под рукой, листать чат вверх не нужно.
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_TOUR), KeyboardButton(text=BTN_EXAMPLES)],
              [KeyboardButton(text=BTN_OWN), KeyboardButton(text=BTN_ERROR)]],
    resize_keyboard=True, is_persistent=True, input_field_placeholder="Кнопка ниже или свои данные",
)
_WELCOME = (
    "Привет! Я демо-бот библиотеки БотГраф: превращаю цифры в график, который читается на телефоне.\n\n"
    f"{BTN_TOUR} — покажу всё, что умею\n"
    f"{BTN_EXAMPLES} — готовые графики: листайте ◀ ▶ и меняйте тему\n"
    f"{BTN_OWN} — нарисую ваши цифры\n"
    f"{BTN_ERROR} — как я объясняю ошибки в данных\n\n"
    "Кнопки — внизу, у поля ввода."
)
_MENU = "Выберите пример. Под картинкой: ◀ ▶ — листать, 🌙 — тема, 🔤 — текстом, { } — данные примера."
_OWN_TEMPLATE = 'bar {"title": "Мой график", "labels": ["Пн", "Вт", "Ср"], "values": [5, 3, 8]}'
_OWN_HELP = (
    "Пришлите данные одним сообщением: вид и тема (можно не писать), потом JSON.\n\n"
    "Шаблон — нажмите на него, чтобы скопировать, поменяйте цифры и отправьте мне:\n"
    f"<pre>{html.escape(_OWN_TEMPLATE, quote=False)}</pre>\n"
    f"Виды: {', '.join(KINDS)}. Темы: {', '.join(THEMES)}.\n"
    "Текстом вместо картинки — начните сообщение с /text.\n"
    "Данные любого примера — кнопка «{ } JSON» под картинкой."
)
ERROR_EXAMPLE = 'bar {"labels": ["Кошки", "Собаки"], "values": [12]}'
_TOUR_START = "Показываю всё за минуту: 7 видов графиков, текстовый режим и как я объясняю ошибки."
_TOUR_END = (
    "Это всё, что умеет БотГраф. Дальше — сами:\n"
    f"{BTN_EXAMPLES} — листайте графики ◀ ▶ и меняйте тему\n"
    f"{BTN_OWN} — нарисую ваши цифры"
)
# «Умная пунктуация» телефона подменяет прямые кавычки на эти.
_SMART_QUOTES = str.maketrans(dict.fromkeys("“”„«»", '"'))
# Бот на маленьком сервере: больше двух рисунков разом только удлиняют очередь.
_DRAWING = asyncio.Semaphore(2)

log = logging.getLogger("botgraph.bot")
dp = Dispatcher()


def parse_request(text: str) -> tuple[str, str, str]:
    """«[вид] [тема] {json}» → (вид, тема, json). Слова до JSON проверяются, чтобы опечатка не ушла молча."""
    head, brace, body = text.partition("{")
    if not brace:
        raise BotGraphValidationError(
            "INVALID_JSON", f"Не вижу JSON — данные должны начинаться с «{{». Шаблон — кнопка «{BTN_OWN}»", "data",
        )
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
    return kind, theme, _straight_quotes(brace + body)


def _straight_quotes(raw: str) -> str:
    """JSON, набранный на телефоне, с кавычками “ ” или « »; «» внутри строк правильного JSON не трогаем."""
    fixed = raw.translate(_SMART_QUOTES)
    return fixed if fixed != raw and not _is_json(raw) and _is_json(fixed) else raw


def _is_json(s: str) -> bool:
    try:
        json.loads(s)
    except ValueError:
        return False
    return True


def example_message(name: str) -> str:
    kind, data = EXAMPLES[name]
    return f"{kind} {json.dumps(data, ensure_ascii=False)}"


def json_message(name: str) -> str:
    # В <pre> Telegram копирует блок одним нажатием — так проще всего начать со своими данными.
    return ("Данные примера. Нажмите на блок, чтобы скопировать, поменяйте цифры и отправьте мне:\n"
            f"<pre>{html.escape(example_message(name), quote=False)}</pre>")


def error_reply(e: BotGraphValidationError) -> str:
    where = f" в поле <code>{html.escape(e.field)}</code>" if e.field else ""
    return f"❌ Не получилось нарисовать: <b>{e.code}</b>{where}\n{html.escape(e.message)}"


def error_example() -> str:
    """Настоящий ответ бота на данные с ошибкой — тот же, что придёт, если отправить их самому."""
    kind, theme, data = parse_request(ERROR_EXAMPLE)
    try:
        validate_payload(data, kind, theme)
    except BotGraphValidationError as e:
        return (f"Если прислать данные с ошибкой (подписи две, а значение одно):\n"
                f"<pre>{html.escape(ERROR_EXAMPLE, quote=False)}</pre>\nя отвечу:\n\n{error_reply(e)}")


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [_button(_TITLES[name], f"v:{name}:light") for name in NAMES]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])


def card_keyboard(name: str, theme: str) -> InlineKeyboardMarkup:
    """Кнопки под картинкой примера; в callback_data всё состояние, так что бот ничего не хранит."""
    i = NAMES.index(name)
    prev_name, next_name = NAMES[i - 1], NAMES[(i + 1) % len(NAMES)]
    other = "light" if theme == "dark" else "dark"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("☀️ Светлая" if theme == "dark" else "🌙 Тёмная", f"v:{name}:{other}"),
         _button("🔤 Текстом", f"t:{name}"), _button("{ } JSON", f"j:{name}")],
        [_button("◀", f"v:{prev_name}:{theme}"), _button("📊 Все примеры", "menu"), _button("▶", f"v:{next_name}:{theme}")],
    ])


def card_caption(name: str) -> str:
    return f"{_TITLES[name]} · {NAMES.index(name) + 1} из {len(NAMES)}"


async def _send(bot: Bot, chat_id: int, data, kind: str, theme: str, *,
                caption: str | None = None, as_text: bool = False, reply_markup=None) -> None:
    """Если Telegram не принял фото, тот же график уходит текстом — пользователь не остаётся без ответа."""
    if not as_text:
        try:
            await send_chart(bot, chat_id, data, kind, theme, caption=caption, reply_markup=reply_markup)
            return
        except TelegramAPIError as e:
            log.warning("фото не отправилось (%s) — отправляю текстом", e)
    await send_chart(bot, chat_id, data, kind, caption=caption, as_text=True, reply_markup=reply_markup)


@dp.message(CommandStart())
@dp.message(Command("help"))
async def start(message: Message) -> None:
    await message.answer(_WELCOME, reply_markup=MAIN_KEYBOARD)


@dp.message(Command("examples"))
@dp.message(F.text == BTN_EXAMPLES)
async def examples(message: Message) -> None:
    await message.answer(_MENU, reply_markup=menu_keyboard())


@dp.message(F.text == BTN_OWN)
async def own_data(message: Message) -> None:
    await message.answer(_OWN_HELP, parse_mode="HTML")


@dp.message(F.text == BTN_ERROR)
async def error_demo(message: Message) -> None:
    await message.answer(error_example(), parse_mode="HTML")


@dp.message(F.text == BTN_TOUR)
async def tour(message: Message, bot: Bot) -> None:
    chat_id = message.chat.id
    await message.answer(_TOUR_START)
    await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    async with _DRAWING:
        pngs = [await draw(data, kind, "light") for kind, data in EXAMPLES.values()]
    await bot.send_media_group(chat_id=chat_id, media=[
        InputMediaPhoto(media=BufferedInputFile(png.getvalue(), filename=f"{name}.png"), caption=_TITLES[name])
        for name, png in zip(NAMES, pngs)
    ])
    kind, data = EXAMPLES["bar"]
    await send_chart(bot, chat_id, data, kind, caption="Тот же график текстом — когда картинку отправить нельзя:",
                     as_text=True)
    await message.answer(error_example(), parse_mode="HTML")
    await message.answer(_TOUR_END)


@dp.callback_query(F.data.startswith("v:"))
async def show_example(query: CallbackQuery, bot: Bot) -> None:
    """Тема и ◀ ▶ меняют ту же картинку на месте, чтобы чат не засорялся; из меню приходит новая."""
    _, name, theme = query.data.split(":")
    await query.answer()
    kind, data = EXAMPLES[name]
    chat_id, caption, markup = query.message.chat.id, card_caption(name), card_keyboard(name, theme)
    async with _DRAWING:
        # У сообщения старше 48 часов Telegram не отдаёт содержимое (InaccessibleMessage) — тогда фото нет.
        if getattr(query.message, "photo", None):
            png = await draw(data, kind, theme)
            media = InputMediaPhoto(media=BufferedInputFile(png.getvalue(), filename="chart.png"), caption=caption)
            try:
                await bot.edit_message_media(media=media, chat_id=chat_id, message_id=query.message.message_id,
                                             reply_markup=markup)
                return
            except TelegramBadRequest as e:
                if "not modified" in str(e):  # двойное нажатие: картинка уже такая
                    return
                log.warning("картинка не заменилась (%s) — присылаю новую", e)
        await _send(bot, chat_id, data, kind, theme, caption=caption, reply_markup=markup)


@dp.callback_query(F.data.startswith("t:"))
async def show_text(query: CallbackQuery, bot: Bot) -> None:
    name = query.data[2:]
    await query.answer()
    kind, data = EXAMPLES[name]
    await send_chart(bot, query.message.chat.id, data, kind, caption=_TITLES[name], as_text=True)


@dp.callback_query(F.data.startswith("j:"))
async def show_json(query: CallbackQuery, bot: Bot) -> None:
    await query.answer()
    await bot.send_message(chat_id=query.message.chat.id, text=json_message(query.data[2:]), parse_mode="HTML")


@dp.callback_query(F.data == "menu")
async def show_menu(query: CallbackQuery, bot: Bot) -> None:
    await query.answer()
    await bot.send_message(chat_id=query.message.chat.id, text=_MENU, reply_markup=menu_keyboard())


@dp.callback_query()
async def stale_button(query: CallbackQuery) -> None:
    await query.answer(f"Эта кнопка от старой версии бота — нажмите «{BTN_EXAMPLES}» внизу", show_alert=True)


@dp.message(F.text)
async def user_data(message: Message, bot: Bot) -> None:
    try:
        kind, theme, data = parse_request(message.text)
        async with _DRAWING:
            await _send(bot, message.chat.id, data, kind, theme, as_text=message.text.startswith("/text"))
    except BotGraphValidationError as e:
        await message.answer(error_reply(e), parse_mode="HTML")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bot = Bot(os.environ["BOT_TOKEN"])
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="examples", description="Готовые примеры графиков"),
        BotCommand(command="help", description="Что умеет бот"),
    ])
    me = await bot.get_me()
    log.info("демо-бот @%s запущен", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
