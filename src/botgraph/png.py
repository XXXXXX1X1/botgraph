"""Функция 2: PNG-картинка для отправки в чат."""

import io
import math
import textwrap
from functools import cache

from matplotlib.figure import Figure
from matplotlib.ft2font import FT2Font
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
from matplotlib.transforms import blended_transform_factory

from . import card, heatmap
from .fmt import format_delta, format_percent, format_value
from .schema import BotGraphValidationError, ChartPayload
from .themes import (
    CENTER_SIZE, DPI, EDGE_PAD_IN, EDGE_PAD_PX, FONT_BOLD, FONT_REGULAR, LABEL_SIZE, THEMES, TICK_PAD_PT, TICK_SIZE,
    TITLE_SIZE, TITLE_WRAP_CHARS, WIDTH_PX, Theme, base_axes, delta_color, fit_width, font, text_width_px,
)
from .validator import validate_payload

_LABEL_PAD_PT = 6
_DELTA_GAP_PX = 18  # между значением и дельтой «▲ 20 %»
_LEGEND_ROW_PX = 64  # строка легенды над графиком сравнения
_LEGEND_HANDLE_PX = 150  # значок легенды и отступы вокруг подписи


def render_png(data, kind: str = "bar", theme: str = "light") -> io.BytesIO:
    """Рисует график и возвращает PNG в памяти, указатель стоит в начале буфера."""
    chart = validate_payload(data, kind, theme)
    _check_glyphs(chart.texts())
    t = THEMES[theme]

    fig = Figure(figsize=(WIDTH_PX / DPI, _HEIGHT[kind](chart) / DPI), dpi=DPI, facecolor=t.surface, layout="constrained")
    fig.get_layout_engine().set(w_pad=EDGE_PAD_IN, h_pad=EDGE_PAD_IN)
    if chart.title:
        fig.suptitle(
            textwrap.fill(chart.title, TITLE_WRAP_CHARS), x=0.03, ha="left",
            color=t.ink, fontproperties=font(TITLE_SIZE, bold=True),
        )
    _DRAW[kind](fig, chart, t)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=t.surface)
    # Фигура держится на циклических ссылках и ждёт редкой полной сборки мусора. На macOS память процесса
    # без очистки росла на ~70 МБ за 500 картинок (на Linux — на 1 МБ в обоих случаях).
    fig.clear()
    buf.seek(0)
    buf.name = "botgraph.png"  # по имени библиотеки ботов определяют тип файла
    return buf


def _check_glyphs(texts: list[tuple[str, str, bool]]) -> None:
    """Символ, которого нет в шрифте, matplotlib рисует квадратиком — лучше сразу сказать об этом."""
    for field, text, bold in texts:
        charmap = _charmap(FONT_BOLD if bold else FONT_REGULAR)
        missing = [ch for ch in text if ord(ch) not in charmap]
        if missing:
            raise BotGraphValidationError(
                "UNSUPPORTED_GLYPH", f"Символ {missing[0]!r} не поддерживается шрифтом DejaVu Sans", field,
            )


@cache
def _charmap(path) -> frozenset[int]:
    return frozenset(FT2Font(str(path)).get_charmap())


def _line_legend_labels(chart: ChartPayload) -> list[str]:
    # Последние значения — в легенде: подпись у точки налезала бы на вторую линию.
    return [f"{chart.current_label}: {format_value(chart.values[-1])}",
            f"{chart.previous_label}: {format_value(chart.previous[-1])}"]


def _legend_rows(labels: list[str]) -> int:
    """Обе подписи в строку, если помещаются по ширине, иначе друг под другом."""
    width = sum(text_width_px(s, TICK_SIZE) + _LEGEND_HANDLE_PX for s in labels)
    return 1 if width <= WIDTH_PX - 2 * EDGE_PAD_PX else len(labels)


def _legend(ax, t: Theme, handles: list) -> None:
    rows = _legend_rows([h.get_label() for h in handles])
    # Над осями (место освобождает constrained layout), но от левого края картинки, а не осей:
    # у столбиков слева колонка названий, и легенда от осей не влезала по ширине.
    # Легенда уровня фигуры (fig.legend "outside") налезает на заголовок.
    ax.legend(
        handles=handles, loc="lower left", bbox_to_anchor=(0.005, 1),
        bbox_transform=blended_transform_factory(ax.figure.transFigure, ax.transAxes),
        ncols=len(handles) // rows, frameon=False, borderaxespad=0.6,
        handlelength=1.4, columnspacing=1.8, prop=font(TICK_SIZE), labelcolor=t.ink_secondary,
    )


def _bar(fig: Figure, chart: ChartPayload, t: Theme) -> None:
    ax = fig.add_subplot()
    base_axes(ax, t)
    n = len(chart.values)
    previous = chart.previous or chart.values
    value_labels = [format_value(v) for v in chart.values]
    value_widths = [text_width_px(s, LABEL_SIZE, bold=True) for s in value_labels]
    deltas = [format_delta(v, p) for v, p in zip(chart.values, previous)] if chart.previous else []
    end_widths = [w + _DELTA_GAP_PX + text_width_px(d, LABEL_SIZE) for w, (d, _) in zip(value_widths, deltas)] or value_widths

    lo, hi = min(0.0, *chart.values, *previous), max(0.0, *chart.values, *previous)
    # Все подписи по одну сторону: слева — только если правее нуля ничего нет. При разных знаках
    # подписи по обе стороны съели бы ширину телефона, а справа от нуля у отрицательной строки пусто.
    side = -1 if hi == 0 and lo < 0 else 1
    value_px = max(end_widths) + (_LABEL_PAD_PT + 6) * DPI / 72
    # Колонка названий уступает место подписям значений.
    label_max = min(WIDTH_PX * 0.36, max(_MIN_LABEL_PX, _PLOT_PX - value_px / _MAX_LABEL_SHARE))
    labels = [fit_width(s, LABEL_SIZE, label_max) for s in chart.labels]

    ax.barh(range(n), chart.values, height=0.56, color=t.series[0])
    ax.set_yticks(range(n), labels=labels, color=t.ink_secondary, fontproperties=font(LABEL_SIZE))
    ax.invert_yaxis()  # первая категория сверху, как в списке
    ax.xaxis.set_visible(False)  # у каждого столбика есть подпись, ось X лишняя
    ax.axvline(0, color=t.baseline, linewidth=1)

    ha = "left" if side > 0 else "right"
    for i, (v, p) in enumerate(zip(chart.values, previous)):
        # Подпись — за дальним концом: столбика, метки прошлого значения или нуля.
        end = max(v, p, 0) if side > 0 else min(v, p)
        ax.annotate(
            value_labels[i], (end, i), xytext=(side * _LABEL_PAD_PT, 0), textcoords="offset points",
            ha=ha, va="center", color=t.ink, fontproperties=font(LABEL_SIZE, bold=True),
        )
        if deltas:
            text, direction = deltas[i]
            shift = _LABEL_PAD_PT + (value_widths[i] + _DELTA_GAP_PX) * 72 / DPI
            ax.annotate(
                text, (end, i), xytext=(side * shift, 0), textcoords="offset points", ha=ha, va="center",
                color=delta_color(t, direction, chart.lower_is_better), fontproperties=font(LABEL_SIZE),
            )
    if chart.previous:
        # Прошлое значение — риской поперёк столбика, как в bullet-графике: видно и рост, и падение.
        ax.vlines(chart.previous, [i - 0.38 for i in range(n)], [i + 0.38 for i in range(n)], color=t.ink, linewidth=2.5)
        _legend(ax, t, [
            Patch(facecolor=t.series[0], label=chart.current_label),
            Line2D([], [], color=t.ink, marker="|", linestyle="none", markersize=14, markeredgewidth=2.5,
                   label=chart.previous_label),
        ])

    label_col = max(text_width_px(s, LABEL_SIZE) for s in labels)
    ax.set_xlim(*_bar_xlim(lo, hi, value_px / (_PLOT_PX - label_col), side))


_PLOT_PX = WIDTH_PX - 2 * EDGE_PAD_PX - TICK_PAD_PT * DPI / 72  # ширина под названия и столбики
_MIN_LABEL_PX = 80
_MAX_LABEL_SHARE = 0.7  # подписи значений занимают не больше 70 % ширины осей, остальное — столбики


def _bar_xlim(lo: float, hi: float, frac: float, side: int) -> tuple[float, float]:
    """Пределы оси X, где со стороны side (1 — справа, −1 — слева) есть доля frac ширины осей под подписи."""
    if lo == hi:
        hi = 1.0
    frac = min(frac, _MAX_LABEL_SHARE)
    pad = (hi - lo) * frac / (1 - frac)
    return (lo, hi + pad) if side > 0 else (lo - pad, hi)


def _line(fig: Figure, chart: ChartPayload, t: Theme) -> None:
    ax = fig.add_subplot()
    base_axes(ax, t)
    n = len(chart.values)
    x = range(n)
    color = t.series[0]

    last = chart.values[-1]
    # Подпись последнего значения ставим с той стороны, откуда линия не приходит.
    label_above = n == 1 or last >= chart.values[-2]
    ticks = _y_ticks(chart.values, None if chart.previous else label_above, chart.previous or ())
    ax.set_ylim(ticks[0], ticks[-1])
    ax.set_yticks(ticks, labels=[format_value(v) for v in ticks], color=t.ink_secondary, fontproperties=font(TICK_SIZE))
    ax.grid(axis="y", color=t.grid, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color(t.baseline)
    ax.spines["bottom"].set_position(("data", ticks[0]))

    if chart.previous:
        # Прошлый период приглушён: он фон для сравнения, а не вторая равноправная серия.
        prev_style = {"color": t.ink_secondary, "alpha": 0.55, "linewidth": 2}
        ax.plot(x, chart.previous, solid_joinstyle="round", solid_capstyle="round", **prev_style)
        current, previous = _line_legend_labels(chart)
        _legend(ax, t, [
            Line2D([], [], color=color, linewidth=2, label=current),
            Line2D([], [], label=previous, **prev_style),
        ])
    ax.fill_between(x, chart.values, ticks[0], color=color, alpha=0.10, linewidth=0)
    marker = "o" if n <= 12 else None  # на длинном ряду точки сливаются в линию
    ax.plot(
        x, chart.values, color=color, linewidth=2, solid_joinstyle="round", solid_capstyle="round",
        marker=marker, markersize=6, markeredgecolor=t.surface, markeredgewidth=1.5,
    )
    ax.plot([n - 1], [last], "o", color=color, markersize=9, markeredgecolor=t.surface, markeredgewidth=2)
    if not chart.previous:
        ax.annotate(
            format_value(last), (n - 1, last),
            xytext=(-4, 12 if label_above else -12), textcoords="offset points",
            ha="right", va="bottom" if label_above else "top",
            color=t.ink, fontproperties=font(LABEL_SIZE, bold=True),
        )

    labels = [fit_width(s, TICK_SIZE, WIDTH_PX * 0.4) for s in chart.labels]
    shown = _spread(n, _x_label_count(labels))
    ax.set_xticks(shown, labels=[labels[i] for i in shown], color=t.ink_secondary, fontproperties=font(TICK_SIZE))
    pad = 0.04 * (n - 1) or 0.5  # одна точка — по центру, а не в нулевом по ширине интервале
    ax.set_xlim(-pad, n - 1 + pad)


def _y_ticks(values: tuple[float, ...], label_above: bool | None, extra: tuple[float, ...] = ()) -> list[float]:
    """Круглые деления оси Y по всем рядам; если последняя точка прижата к краю, где стоит её подпись, — ещё одно деление.

    label_above=None — подписи у последней точки нет.
    """
    lo, hi = min(values + extra), max(values + extra)
    if lo == hi:
        step = abs(lo) * 0.1 or 1.0
        lo, hi = lo - step, hi + step
    ticks = list(MaxNLocator(nbins=4).tick_values(lo, hi))
    step = ticks[1] - ticks[0]
    room = (ticks[-1] - values[-1]) if label_above else (values[-1] - ticks[0])
    if label_above is not None and room < 0.15 * (ticks[-1] - ticks[0]):
        if label_above:
            ticks.append(ticks[-1] + step)
        else:
            ticks.insert(0, ticks[0] - step)
    return ticks


def _x_label_count(labels: list[str]) -> int:
    """Сколько подписей помещается по ширине без наложения (по самой широкой)."""
    label_px = max(text_width_px(s, TICK_SIZE) for s in labels) + 50
    return max(2, min(6, int(WIDTH_PX * 0.9 // label_px)))


def _spread(n: int, k: int) -> list[int]:
    """Не больше k индексов из n с ровным шагом; отсчёт от конца — последняя точка подписана всегда."""
    step = math.ceil((n - 1) / (k - 1)) if n > k else 1
    return list(range(n - 1, -1, -step))[::-1]


_PIE_PX = 760
_PIE_ROW_PX = 82


def _pie(fig: Figure, chart: ChartPayload, t: Theme) -> None:
    n = len(chart.values)
    pie_ax, legend_ax = fig.subplots(2, 1, height_ratios=[_PIE_PX, n * _PIE_ROW_PX])
    colors = t.series[:n]
    total = sum(chart.values)

    pie_ax.pie(
        chart.values, colors=colors, startangle=90, counterclock=False,
        wedgeprops={"width": 0.36, "edgecolor": t.surface, "linewidth": 2},
    )
    pie_ax.text(0, 0.08, format_value(total), ha="center", va="center", color=t.ink, fontproperties=font(CENTER_SIZE, bold=True))
    pie_ax.text(0, -0.2, "всего", ha="center", va="center", color=t.ink_secondary, fontproperties=font(TICK_SIZE))

    # Легенда: квадратик (x=0.04), подпись (с 0.09) и значение с процентом (прижато к 0.96).
    legend_ax.set_axis_off()
    legend_ax.set_xlim(0, 1)
    legend_ax.set_ylim(n, 0)
    amounts = [f"{format_value(v)} · {format_percent(v, total)}" for v in chart.values]
    legend_px = WIDTH_PX - 2 * EDGE_PAD_PX
    label_px = legend_px * (0.96 - 0.09) - max(text_width_px(s, LABEL_SIZE) for s in amounts) - 40
    for i, (label, amount, color) in enumerate(zip(chart.labels, amounts, colors)):
        y = i + 0.5
        legend_ax.plot([0.04], [y], "s", color=color, markersize=13)
        legend_ax.text(0.09, y, fit_width(label, LABEL_SIZE, label_px), va="center", color=t.ink, fontproperties=font(LABEL_SIZE))
        legend_ax.text(0.96, y, amount, ha="right", va="center", color=t.ink_secondary, fontproperties=font(LABEL_SIZE))


_DRAW = {"bar": _bar, "line": _line, "pie": _pie, "calendar": heatmap.draw, "card": card.draw}
_HEIGHT = {
    "bar": lambda c: max(480, 240 + len(c.values) * 84) + (
        _legend_rows([c.current_label, c.previous_label]) * _LEGEND_ROW_PX if c.previous else 0),
    "line": lambda c: 760 + (_legend_rows(_line_legend_labels(c)) * _LEGEND_ROW_PX if c.previous else 0),
    "pie": lambda c: _PIE_PX + 140 + len(c.values) * _PIE_ROW_PX,
    "calendar": heatmap.height,
    "card": card.height,
}
