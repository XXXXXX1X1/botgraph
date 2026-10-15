"""Запись чисел и текстовая вёрстка по-русски — общие для картинки и текста."""

_BIG = ((1e12, "трлн"), (1e9, "млрд"), (1e6, "млн"))
_SPARK = "▁▂▃▄▅▆▇█"


def format_value(v: float) -> str:
    """12 → «12», 12345 → «12 345», 3.14159 → «3,14», 1500000 → «1,5 млн»."""
    for limit, suffix in _BIG:
        if abs(v) >= limit:
            return f"{_num(v / limit, 1)} {suffix}"
    return _num(v, 0 if abs(v) >= 100 else 2)


def format_percent(part: float, total: float) -> str:
    pct = part / total * 100
    if 0 < pct < 1:
        return "<1 %"
    return f"{round(pct)} %"


def format_delta(current: float, previous: float) -> tuple[str, int]:
    """«▲ 20 %» и направление: 1 — рост, −1 — падение, 0 — без изменений."""
    diff = current - previous
    if diff == 0:
        return "= 0 %", 0
    arrow, direction = ("▲", 1) if diff > 0 else ("▼", -1)
    if previous == 0:  # процент от нуля не определён — показываем разницу
        return f"{arrow} {'+' if diff > 0 else '−'}{format_value(abs(diff))}", direction
    pct = abs(diff) / abs(previous) * 100
    return f"{arrow} {'<1' if pct < 1 else format_value(round(pct))} %", direction


def delta_note(previous_label: str) -> str:
    """Пояснение под текстовой таблицей: в тексте нет цвета, остаются стрелки."""
    return f"▲▼ — изменение к «{previous_label}»"


def sparkline(values) -> str:
    """Мини-график из символов ▁▂▃▄▅▆▇█."""
    lo, hi = min(values), max(values)
    if lo == hi:
        return _SPARK[3] * len(values)
    return "".join(_SPARK[round((v - lo) / (hi - lo) * (len(_SPARK) - 1))] for v in values)


def columns(first: list[str], *cols: list[str]) -> list[str]:
    """Первая колонка (подписи) прижата влево, остальные (числа) — вправо."""
    first_w = max(len(s) for s in first)
    widths = [max(len(s) for s in col) for col in cols]
    return [
        "  ".join([head.ljust(first_w)] + [cell.rjust(w) for cell, w in zip(cells, widths)]).rstrip()
        for head, *cells in zip(first, *cols)
    ]


def _num(x: float, digits: int) -> str:
    x = round(x, digits) + 0.0  # + 0.0 убирает «−0»
    s = f"{x:,.{digits}f}"
    if digits:
        s = s.rstrip("0").rstrip(".")
    return s.replace(",", " ").replace(".", ",").replace("-", "−")
