"""БотГраф: словарь с данными → читаемый на телефоне график для чат-бота."""

from .png import render_png
from .schema import BotGraphValidationError, ChartPayload
from .text import render_text
from .validator import validate_payload

__all__ = ["render_png", "render_text", "validate_payload", "ChartPayload", "BotGraphValidationError"]
__version__ = "0.3.0"
