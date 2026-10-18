"""validate_payload — единая проверка данных: её вызывают render_png и render_text, можно и напрямую."""

from .card import CardPayload, validate_card
from .schema import KINDS, BotGraphValidationError, ChartPayload, validate_chart
from .themes import THEMES


def validate_payload(data, kind: str = "bar", theme: str = "light") -> ChartPayload | CardPayload:
    """Проверяет и нормализует данные. Ошибка — BotGraphValidationError с кодом, полем и подсказкой."""
    if kind not in KINDS:
        raise BotGraphValidationError(
            "UNSUPPORTED_KIND", f"Неподдерживаемый тип графика {kind!r}. Допустимые значения: {', '.join(KINDS)}", "kind",
        )
    if theme not in tuple(THEMES):
        raise BotGraphValidationError(
            "UNSUPPORTED_THEME", f"Неподдерживаемая тема {theme!r}. Допустимые значения: {', '.join(THEMES)}", "theme",
        )
    return validate_card(data, theme) if kind == "card" else validate_chart(data, kind, theme)
