"""БотГраф: словарь с данными → читаемый на телефоне график для чат-бота."""

from .png import render_png
from .schema import ChartError
from .text import render_text

__all__ = ["render_png", "render_text", "ChartError"]
__version__ = "0.2.0"
