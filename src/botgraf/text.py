"""Функция 3: текстовый вариант, когда картинку отправить нельзя.

Колонки выравниваются пробелами, поэтому в чат текст нужно отправлять моноширинным
(например, в <pre> при parse_mode="HTML").
"""

from . import card, heatmap
from .fmt import columns, delta_note, format_delta, format_percent, format_value
from .schema import ChartData, check_kind, validate

BAR_CELLS = 10
_EIGHTHS = " ▏▎▍▌▋▊▉"


def render_text(data, kind: str = "bar") -> str:
    check_kind(kind)
    chart = card.validate_card(data) if kind == "card" else validate(data, kind)
    lines = [chart.title] if chart.title else []
    lines += _RENDER[kind](chart)
    return "\n".join(lines)


def _bar(chart: ChartData) -> list[str]:
    scale = max(abs(v) for v in chart.values) or 1.0
    bars = [_bar_cells(abs(v) / scale * BAR_CELLS).ljust(BAR_CELLS) for v in chart.values]
    values = [format_value(v) for v in chart.values]
    if not chart.previous:
        return columns(chart.labels, bars, values)
    deltas = [format_delta(v, p)[0] for v, p in zip(chart.values, chart.previous)]
    return columns(chart.labels, bars, values, deltas) + [delta_note(chart.previous_label)]


def _bar_cells(cells: float) -> str:
    full, rest = divmod(round(cells * 8), 8)
    return "█" * full + (_EIGHTHS[rest] if rest else "")


def _line(chart: ChartData) -> list[str]:
    values = [format_value(v) for v in chart.values]
    if not chart.previous:
        return columns(chart.labels, values)
    return columns(
        ["", *chart.labels],
        [chart.current_label, *values],
        [chart.previous_label, *(format_value(v) for v in chart.previous)],
        ["", *(format_delta(v, p)[0] for v, p in zip(chart.values, chart.previous))],
    )


def _pie(chart: ChartData) -> list[str]:
    total = sum(chart.values)
    rows = columns(
        chart.labels, [format_value(v) for v in chart.values], [format_percent(v, total) for v in chart.values],
    )
    return rows + [f"Всего: {format_value(total)}"]


def _calendar(chart: ChartData) -> list[str]:
    g = heatmap.grid(chart)
    top = max(chart.values)
    rows = [[" "] * g.weeks for _ in range(7)]
    for d in g.days():
        col, row = g.cell(d)
        rows[row][col] = heatmap.TEXT_CELLS[heatmap.level(g.by_day.get(d, 0), top)]
    marked, days, streak = heatmap.summary(g)
    return [f"{name} {''.join(cells)}".rstrip() for name, cells in zip(heatmap.WEEKDAYS, rows)] + [
        f"{g.first:%d.%m.%Y} – {g.last:%d.%m.%Y}",
        f"Отмечено {marked} из {days} дн. · серия {streak} дн.",
        f"{heatmap.TEXT_CELLS[0]} — нет, {heatmap.TEXT_CELLS[1:]} — меньше → больше",
    ]


_RENDER = {"bar": _bar, "line": _line, "pie": _pie, "calendar": _calendar, "card": card.card_text}
