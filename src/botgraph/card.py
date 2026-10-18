"""Карточка дня (kind="card"): 1–4 главных числа со сравнением и мини-график под ними.

Формат данных свой:
{"title": "Итоги дня", "previous_label": "вчера",
 "metrics": [{"label": "Выручка", "value": 48000, "previous": 43000, "unit": "₽", "lower_is_better": false}],
 "trend": {"label": "Выручка за 2 недели", "labels": [...], "values": [...]}}
"""

import math
from dataclasses import dataclass, replace

from matplotlib.figure import Figure

from .fmt import columns, delta_note, format_delta, format_value, sparkline
from .schema import (
    MAX_TITLE_LEN, BotGraphValidationError, ChartPayload, as_dict, flag, number, optional_text, reject_unknown,
    required_list, text, validate_chart,
)
from .themes import (
    DPI, EDGE_PAD_PX, LABEL_SIZE, TICK_SIZE, WIDTH_PX, Theme, base_axes, delta_color, fit_width, font, text_width_px,
)

MAX_METRICS = 4
MAX_UNIT_LEN = 6
_FIELDS = ("title", "previous_label", "metrics", "trend")
_METRIC_FIELDS = ("label", "value", "previous", "unit", "lower_is_better")
_TREND_FIELDS = ("label", "labels", "values")

_TILE_PX = 300
_TREND_PX = 360
_TREND_DECOR_PX = 160  # подпись над мини-графиком и даты под ним — сверх высоты самого графика
_VALUE_SIZE = 32  # крупное число; если не влезает в колонку — уменьшаем
_MIN_VALUE_SIZE = 16


@dataclass(frozen=True)
class Metric:
    label: str
    value: float
    previous: float | None = None
    unit: str | None = None
    lower_is_better: bool = False

    def formatted(self, v: float | None = None) -> str:
        s = format_value(self.value if v is None else v)
        return f"{s} {self.unit}" if self.unit else s


@dataclass(frozen=True)
class CardPayload:
    title: str | None
    previous_label: str
    metrics: tuple[Metric, ...]
    trend: ChartPayload | None  # мини-график — та же линия, её title — подпись над ним
    theme: str
    kind: str = "card"

    def texts(self) -> list[tuple[str, str, bool]]:
        texts = [("previous_label", self.previous_label, False)]
        if self.title:
            texts.append(("title", self.title, True))
        for i, m in enumerate(self.metrics):
            texts += [(f"metrics[{i}].label", m.label, False), (f"metrics[{i}]", m.formatted(), True)]
        if self.trend:
            # В данных подпись мини-графика называется label, внутри ChartPayload — title.
            texts += [(f"trend.{'label' if field == 'title' else field}", s, False) for field, s, _ in self.trend.texts()]
        return texts


def validate_card(data, theme: str) -> CardPayload:
    data = as_dict(data)
    reject_unknown(data, _FIELDS)
    raw = required_list(data, "metrics")
    if not raw:
        raise BotGraphValidationError("EMPTY_DATA", "Нужна хотя бы одна метрика", "metrics")
    if len(raw) > MAX_METRICS:
        raise BotGraphValidationError("TOO_MANY_ITEMS", f"Максимум {MAX_METRICS} метрики, получено {len(raw)}", "metrics")
    return CardPayload(
        title=optional_text("title", data.get("title"), MAX_TITLE_LEN),
        previous_label=text("previous_label", data["previous_label"], "вчера") if "previous_label" in data else "вчера",
        metrics=tuple(_metric(i, m) for i, m in enumerate(raw)),
        trend=_trend(data["trend"], theme) if data.get("trend") is not None else None,
        theme=theme,
    )


def _metric(i: int, m) -> Metric:
    path = f"metrics[{i}]"
    if not isinstance(m, dict):
        raise BotGraphValidationError("INVALID_TYPE", f"Ожидается словарь, получено {type(m).__name__}", path)
    reject_unknown(m, _METRIC_FIELDS, path)
    for key in ("label", "value"):
        if key not in m:
            raise BotGraphValidationError("MISSING_KEY", "Отсутствует обязательное поле", f"{path}.{key}")
    return Metric(
        label=text(f"{path}.label", m["label"], f"#{i + 1}"),
        value=number(f"{path}.value", m["value"]),
        previous=number(f"{path}.previous", m["previous"]) if m.get("previous") is not None else None,
        unit=text(f"{path}.unit", m["unit"], None, MAX_UNIT_LEN) if "unit" in m else None,
        lower_is_better=flag(f"{path}.lower_is_better", m["lower_is_better"]) if "lower_is_better" in m else False,
    )


def _trend(trend, theme: str) -> ChartPayload:
    if not isinstance(trend, dict):
        raise BotGraphValidationError("INVALID_TYPE", f"Ожидается словарь, получено {type(trend).__name__}", "trend")
    reject_unknown(trend, _TREND_FIELDS, "trend")
    label = optional_text("trend.label", trend.get("label"), MAX_TITLE_LEN)
    try:
        line = validate_chart({k: v for k, v in trend.items() if k != "label"}, "line", theme)
    except BotGraphValidationError as e:
        raise BotGraphValidationError(e.code, e.message, f"trend.{e.field}") from None
    # Мини-график подписан по краям периода — из одной точки периода нет.
    if len(line.values) < 2:
        raise BotGraphValidationError("TOO_FEW_ITEMS", "Для мини-графика нужно минимум 2 значения", "trend.values")
    return replace(line, title=label)


def height(card: CardPayload) -> int:
    rows = math.ceil(len(card.metrics) / _columns(card))
    return (130 if card.title else 30) + rows * _TILE_PX + (_TREND_PX + _TREND_DECOR_PX if card.trend else 0)


def _columns(card: CardPayload) -> int:
    return 1 if len(card.metrics) == 1 else 2


def draw(fig: Figure, card: CardPayload, t: Theme) -> None:
    cols = _columns(card)
    rows = math.ceil(len(card.metrics) / cols)
    if card.trend:
        tiles, trend_ax = fig.subplots(2, 1, height_ratios=[rows * _TILE_PX, _TREND_PX])
        _trend_chart(trend_ax, card.trend, t)
    else:
        tiles = fig.add_subplot()
    tiles.set_axis_off()
    tiles.set_xlim(0, cols)
    tiles.set_ylim(rows, 0)
    col_px = (WIDTH_PX - 2 * EDGE_PAD_PX) / cols - 40
    for i, m in enumerate(card.metrics):
        _tile(tiles, (i % cols, i // cols), m, card.previous_label, col_px, t)


def _tile(ax, anchor: tuple[int, int], m: Metric, previous_label: str, col_px: float, t: Theme) -> None:
    """Подпись, крупное число, дельта и прошлое значение — сверху вниз от левого верхнего угла плитки."""
    def line(y_px: float, s: str, color: str, size: float, bold: bool = False) -> None:
        ax.annotate(s, anchor, xytext=(0, -y_px * 72 / DPI), textcoords="offset points", va="top",
                    color=color, fontproperties=font(size, bold))

    line(10, fit_width(m.label, LABEL_SIZE, col_px), t.ink_secondary, LABEL_SIZE)
    value = m.formatted()
    size = _VALUE_SIZE
    while size > _MIN_VALUE_SIZE and text_width_px(value, size, bold=True) > col_px:
        size -= 1
    line(62, value, t.ink, size, bold=True)
    if m.previous is not None:
        delta, direction = format_delta(m.value, m.previous)
        line(160, delta, delta_color(t, direction, m.lower_is_better), LABEL_SIZE, bold=True)
        line(212, fit_width(f"{previous_label}: {m.formatted(m.previous)}", TICK_SIZE, col_px), t.ink_secondary, TICK_SIZE)


def _trend_chart(ax, trend: ChartPayload, t: Theme) -> None:
    """Мини-график без осей: форма ряда, последнее значение и края периода."""
    base_axes(ax, t)
    n = len(trend.values)
    lo, hi = min(trend.values), max(trend.values)
    span = (hi - lo) or abs(hi) or 1.0
    floor = lo - span * 0.15
    ax.set_ylim(floor, hi + span * 0.4)  # сверху место под подпись последнего значения
    ax.set_xlim(-0.03 * (n - 1), (n - 1) * 1.03)
    ax.yaxis.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color(t.baseline)
    color = t.series[0]
    ax.fill_between(range(n), trend.values, floor, color=color, alpha=0.10, linewidth=0)
    ax.plot(range(n), trend.values, color=color, linewidth=2, solid_joinstyle="round", solid_capstyle="round")
    ax.plot([n - 1], [trend.values[-1]], "o", color=color, markersize=9, markeredgecolor=t.surface, markeredgewidth=2)
    ax.annotate(format_value(trend.values[-1]), (n - 1, trend.values[-1]), xytext=(-4, 12), textcoords="offset points",
                ha="right", va="bottom", color=t.ink, fontproperties=font(LABEL_SIZE, bold=True))
    ends = [fit_width(trend.labels[i], TICK_SIZE, WIDTH_PX * 0.4) for i in (0, n - 1)]
    ax.set_xticks([0, n - 1], labels=ends, color=t.ink_secondary, fontproperties=font(TICK_SIZE))
    ax.get_xticklabels()[0].set_horizontalalignment("left")
    ax.get_xticklabels()[1].set_horizontalalignment("right")
    if trend.title:
        ax.set_title(trend.title, loc="left", color=t.ink_secondary, fontproperties=font(LABEL_SIZE), pad=14)


def card_text(card: CardPayload) -> list[str]:
    deltas = [format_delta(m.value, m.previous)[0] if m.previous is not None else "" for m in card.metrics]
    lines = columns([m.label for m in card.metrics], [m.formatted() for m in card.metrics], deltas)
    if any(deltas):
        lines.append(delta_note(card.previous_label))
    if card.trend:
        lines += ["", card.trend.title or "Динамика", f"{sparkline(card.trend.values)}  {format_value(card.trend.values[-1])}"]
    return lines
