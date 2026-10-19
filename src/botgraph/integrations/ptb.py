"""Адаптер для python-telegram-bot 20+."""

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
    # PTB сам принимает файловый объект, обёртка не нужна.
    return await bot.send_photo(chat_id=chat_id, photo=await draw(data, kind, theme), caption=caption,
                                reply_markup=reply_markup)
