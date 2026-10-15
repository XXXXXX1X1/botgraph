"""Пресеты оформления. Пользователь выбирает только имя темы."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import matplotlib
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import text_to_path

WIDTH_PX = 1080
DPI = 200
EDGE_PAD_IN = 0.12  # поля картинки
EDGE_PAD_PX = EDGE_PAD_IN * DPI
TICK_PAD_PT = 8
TITLE_WRAP_CHARS = 28  # жирный заголовок длиннее не помещается в строку шириной 1080 px

# Размеры в пунктах при DPI 200: на экране телефона картинка ужимается примерно втрое.
TITLE_SIZE = 19
LABEL_SIZE = 15
TICK_SIZE = 14
CENTER_SIZE = 28

_FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
# Шрифт задаём файлом, а не через rcParams: глобальные настройки пользователя
# не влияют на картинку, и параллельные вызовы из потоков не мешают друг другу.
FONT_REGULAR = _FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = _FONT_DIR / "DejaVuSans-Bold.ttf"


@cache
def font(size: float, bold: bool = False) -> FontProperties:
    return FontProperties(fname=FONT_BOLD if bold else FONT_REGULAR, size=size)


def text_width_px(text: str, size: float, bold: bool = False) -> float:
    """Ширина строки на картинке, измеренная по шрифту, — чтобы заранее оставить место под подписи."""
    width_pt, _, _ = text_to_path.get_text_width_height_descent(text, font(size, bold), ismath=False)
    return width_pt * DPI / 72


def fit_width(text: str, size: float, max_px: float) -> str:
    """Обрезает строку с «…», чтобы она уместилась в max_px (широкие буквы вроде «Ш» занимают больше места)."""
    if text_width_px(text, size) <= max_px:
        return text
    text = text.removesuffix("…")
    while len(text) > 1 and text_width_px(text + "…", size) > max_px:
        text = text[:-1]
    return text.rstrip() + "…"


@dataclass(frozen=True)
class Theme:
    surface: str
    ink: str
    ink_secondary: str
    grid: str
    baseline: str
    series: tuple[str, ...]
    good: str  # дельта в лучшую сторону; всегда рядом стрелка ▲▼, не только цвет
    bad: str
    heat: tuple[str, ...]  # календарь: 4 уровня одного синего, от меньшего к большему


# Категориальная палитра проверена на различимость при дальтонизме для соседних цветов.
THEMES = {
    "light": Theme(
        surface="#fcfcfb",
        ink="#0b0b0b",
        ink_secondary="#52514e",
        grid="#e1e0d9",
        baseline="#c3c2b7",
        series=("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"),
        good="#006300",
        bad="#d03b3b",
        heat=("#86b6ef", "#5598e7", "#2a78d6", "#184f95"),
    ),
    "dark": Theme(
        surface="#1a1a19",
        ink="#ffffff",
        ink_secondary="#c3c2b7",
        grid="#2c2c2a",
        baseline="#383835",
        series=("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"),
        good="#0ca30c",
        bad="#e66767",
        heat=("#184f95", "#256abf", "#3987e5", "#86b6ef"),
    ),
}


def base_axes(ax, t: Theme) -> None:
    ax.set_facecolor(t.surface)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0, pad=TICK_PAD_PT)


def delta_color(theme: Theme, direction: int, lower_is_better: bool) -> str:
    if direction == 0:
        return theme.ink_secondary
    return theme.good if (direction > 0) != lower_is_better else theme.bad
