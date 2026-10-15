"""Календарь-тепловая карта."""

import re
from datetime import date, timedelta

import pytest

from botgraf import ChartError, render_text
from botgraf.heatmap import grid, level, summary
from botgraf.schema import CALENDAR_MAX_DAYS, validate


def _days(start: date, n: int) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def test_dates_parsed_in_any_order():
    chart = validate({"labels": ["2026-10-14", "2026-10-12"], "values": [1, 2]}, "calendar")
    assert chart.dates == (date(2026, 10, 14), date(2026, 10, 12))


@pytest.mark.parametrize(
    ("labels", "values", "message"),
    [
        (["14.10.2026"], [1], "labels[0]: для calendar нужна дата в формате ГГГГ-ММ-ДД"),
        (["2026-02-30"], [1], "labels[0]: для calendar нужна дата"),
        (["2026-10-14", "2026-10-14"], [1, 2], "даты в labels не должны повторяться"),
        (["2026-10-14"], [-1], "для calendar значения не могут быть отрицательными"),
        (["2026-01-01", "2026-07-02"], [1, 1], f"укладываться в {CALENDAR_MAX_DAYS} дн., сейчас 183"),
    ],
)
def test_invalid_calendar(labels, values, message):
    with pytest.raises(ChartError, match=re.escape(message)):
        validate({"labels": labels, "values": values}, "calendar")


def test_span_limit_is_inclusive():
    validate({"labels": ["2026-01-01", "2026-07-01"], "values": [1, 1]}, "calendar")  # ровно 182 дня


def test_grid_starts_on_monday_and_counts_weeks():
    g = grid(validate({"labels": ["2026-10-14", "2026-10-26"], "values": [1, 1]}, "calendar"))  # ср и пн
    assert g.start == date(2026, 10, 12)
    assert g.weeks == 3
    assert g.cell(date(2026, 10, 26)) == (2, 0)


@pytest.mark.parametrize(("v", "expected"), [(0, 0), (0.1, 1), (25, 1), (26, 2), (75, 3), (76, 4), (100, 4)])
def test_level_is_quarter_of_max(v, expected):
    assert level(v, 100) == expected


def test_summary_counts_marked_days_and_streak_to_last_day():
    labels = _days(date(2026, 10, 1), 6)
    g = grid(validate({"labels": labels[:2] + labels[3:], "values": [1, 1, 2, 2, 2]}, "calendar"))  # 3-го пропуск
    assert summary(g) == (5, 6, 3)


def test_calendar_text():
    text = render_text({"title": "Спорт", "labels": _days(date(2026, 10, 12), 3), "values": [1, 0, 4]}, kind="calendar")
    assert text == (
        "Спорт\n"
        "Пн ░\n"
        "Вт ·\n"
        "Ср █\n"
        "Чт\n"
        "Пт\n"
        "Сб\n"
        "Вс\n"
        "12.10.2026 – 14.10.2026\n"
        "Отмечено 2 из 3 дн. · серия 1 дн.\n"
        "· — нет, ░▒▓█ — меньше → больше"
    )
