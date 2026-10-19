"""Адаптер для aiogram 3."""

from aiogram.types import BufferedInputFile

from . import draw, html_text


async def send_chart(bot, chat_id, data, kind: str = "bar", theme: str = "light", *,
                     caption: str | None = None, as_text: bool = False, reply_markup=None):
    """Отправляет график фото (или текстом при as_text=True) и возвращает отправленное сообщение.

    reply_markup — кнопки под сообщением, как в send_photo.
    Ошибка в данных — BotGraphValidationError до отправки, в чат ничего не уходит.
    """
    if as_text:
        return await bot.send_message(chat_id=chat_id, text=html_text(data, kind, caption), parse_mode="HTML",
                                      reply_markup=reply_markup)
    png = await draw(data, kind, theme)
    photo = BufferedInputFile(png.getvalue(), filename="chart.png")
    return await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption,
                                reply_markup=reply_markup)
