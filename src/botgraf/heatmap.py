"""Календарь-тепловая карта (kind="calendar"): дни по неделям, цвет — величина, как вклады на GitHub."""

import math
from dataclasses import dataclass
from datetime import date, timedelta

from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch

from .schema import ChartData
from .themes import DPI, EDGE_PAD_PX, LABEL_SIZE, TICK_SIZE, WIDTH_PX, Theme, base_axes, font, text_width_px

MONTHS = ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
LEVELS = 4
TEXT_CELLS = "·░▒▓█"  # уровень 0…4 в текстовом варианте

_MIN_COLUMNS = 12  # короткий период не растягиваем во всю ширину — клетки стали бы огромными
_DAY_LABEL_PX = 90
_ALL_DAYS_FROM_PX = 50  # клетка выше этого — подписываем все дни недели, иначе Пн, Ср, Пт
_FOOTER_PX = 190
_CELL_GAP = 0.08  # доля клетки: зазор цвета фона между соседями


@dataclass(frozen=True)
class Grid:
    first: date
    last: date
    start: date  # понедельник первой недели
    weeks: int
    by_day: dict[date, float]

    def days(self):
        for i in range((self.last - self.first).days + 1):
            yield self.first + timedelta(days=i)

    def cell(self, d: date) -> tuple[int, int]:
        """(неделя, день недели) — колонка и строка клетки."""
        return (d - self.start).days // 7, d.weekday()


def grid(chart: ChartData) -> Grid:
    first, last = min(chart.dates), max(chart.dates)
    start = first - timedelta(days=first.weekday())
    return Grid(first, last, start, (last - start).days // 7 + 1, dict(zip(chart.dates, chart.values)))


def level(v: float, top: float) -> int:
    """0 — нет значения, 1…4 — четверти от максимума."""
    return math.ceil(v / top * LEVELS) if v > 0 else 0


def summary(g: Grid) -> tuple[int, int, int]:
    """(дней со значением, дней в периоде, серия подряд до последнего дня)."""
    days = list(g.days())
    marked = sum(1 for d in days if g.by_day.get(d, 0) > 0)
    streak = 0
    for d in reversed(days):
        if g.by_day.get(d, 0) <= 0:
            break
        streak += 1
    return marked, len(days), streak


def _cell_px(weeks: int) -> float:
    return (WIDTH_PX - 2 * EDGE_PAD_PX - _DAY_LABEL_PX) / max(weeks, _MIN_COLUMNS)


def height(chart: ChartData) -> int:
    return round((130 if chart.title else 30) + 70 + 7 * _cell_px(grid(chart).weeks) + _FOOTER_PX)


def draw(fig: Figure, chart: ChartData, t: Theme) -> None:
    g = grid(chart)
    cell_px = _cell_px(g.weeks)
    ax, foot = fig.subplots(2, 1, height_ratios=[7 * cell_px, _FOOTER_PX])
    base_axes(ax, t)
    ax.set_xlim(0, max(g.weeks, _MIN_COLUMNS))
    ax.set_ylim(7, 0)
    ax.set_aspect("equal", anchor="NW")

    top = max(chart.values)
    colors = (t.grid,) + t.heat
    for d in g.days():
        col, row = g.cell(d)
        ax.add_patch(FancyBboxPatch(
            (col + _CELL_GAP, row + _CELL_GAP), 1 - 2 * _CELL_GAP, 1 - 2 * _CELL_GAP,
            boxstyle="round,pad=0,rounding_size=0.18", facecolor=colors[level(g.by_day.get(d, 0), top)], linewidth=0,
        ))

    rows = range(7) if cell_px >= _ALL_DAYS_FROM_PX else (0, 2, 4)
    ax.set_yticks([r + 0.5 for r in rows], labels=[WEEKDAYS[r] for r in rows], color=t.ink_secondary, fontproperties=font(TICK_SIZE))
    months = _month_columns(g)
    ax.xaxis.tick_top()
    ax.set_xticks([c + _CELL_GAP for c, _ in months], labels=[m for _, m in months], color=t.ink_secondary, fontproperties=font(TICK_SIZE))
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("left")

    _footer(foot, g, t)


def _month_columns(g: Grid) -> list[tuple[int, str]]:
    """Подписи месяцев над колонкой, где месяц начинается; первый — если не налезает на следующий."""
    starts = [(g.cell(d)[0], MONTHS[d.month - 1]) for d in g.days() if d.day == 1]
    if not starts or starts[0][0] >= 3:
        starts.insert(0, (0, MONTHS[g.first.month - 1]))
    return starts


def _footer(ax, g: Grid, t: Theme) -> None:
    """Итог периода и шкала «меньше ■■■■■ больше»."""
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(2, 0)
    marked, days, streak = summary(g)
    regular, small = font(LABEL_SIZE), font(TICK_SIZE)
    ax.text(0, 0.5, f"Отмечено {marked} из {days} дн.", va="center", color=t.ink, fontproperties=regular)
    ax.text(1, 0.5, f"Серия: {streak} дн.", ha="right", va="center", color=t.ink, fontproperties=regular)

    x_pt = 0.0
    parts = [("меньше", t.ink_secondary, small)] + [("■", c, font(LABEL_SIZE * 1.6)) for c in (t.grid,) + t.heat]
    parts.append(("больше", t.ink_secondary, small))
    for text, color, prop in parts:
        ax.annotate(text, (0, 1.4), xytext=(x_pt, 0), textcoords="offset points", va="center", color=color, fontproperties=prop)
        x_pt += (text_width_px(text, prop.get_size()) + 10) * 72 / DPI
