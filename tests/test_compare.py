"""Сравнение с прошлым периодом: столбики с меткой «было» и две линии."""

import pytest

from botgraph import BotGraphValidationError, render_text, validate_payload
from botgraph.fmt import format_delta
from botgraph.themes import THEMES, delta_color

BASE = {"labels": ["a", "b"], "values": [12, 8]}


def test_previous_fields_parsed_with_defaults():
    chart = validate_payload({**BASE, "previous": [10, 8]}, "bar")
    assert chart.previous == (10.0, 8.0)
    assert (chart.previous_label, chart.current_label, chart.lower_is_better) == ("раньше", "сейчас", False)
    chart = validate_payload({**BASE, "previous": [10, 8], "previous_label": " вчера ", "lower_is_better": True}, "line")
    assert (chart.previous_label, chart.lower_is_better) == ("вчера", True)


@pytest.mark.parametrize(
    ("data", "kind", "code", "field"),
    [
        ({**BASE, "previous": [1]}, "bar", "LENGTH_MISMATCH", "previous"),
        ({**BASE, "previous": [1, "2"]}, "bar", "INVALID_VALUE_TYPE", "previous[1]"),
        ({**BASE, "previous": 5}, "bar", "INVALID_TYPE", "previous"),
        ({**BASE, "previous": [1, 2]}, "pie", "UNSUPPORTED_COMPARISON", "previous"),
        ({**BASE, "previous_label": "вчера"}, "bar", "MISSING_KEY", "previous"),
        ({**BASE, "previous": [1, 2], "lower_is_better": "да"}, "bar", "INVALID_TYPE", "lower_is_better"),
    ],
)
def test_invalid_comparison(data, kind, code, field):
    with pytest.raises(BotGraphValidationError) as e:
        validate_payload(data, kind)
    assert (e.value.code, e.value.field) == (code, field)


def test_empty_series_name_falls_back_to_default():
    chart = validate_payload({**BASE, "previous": [1, 2], "current_label": " ", "previous_label": "\n"})
    assert (chart.current_label, chart.previous_label) == ("сейчас", "раньше")


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        (12, 10, ("▲ 20 %", 1)),
        (8, 10, ("▼ 20 %", -1)),
        (5, 5, ("= 0 %", 0)),
        (12, 0, ("▲ +12", 1)),  # процент от нуля не определён
        (-3, 0, ("▼ −3", -1)),
        (1001, 1000, ("▲ <1 %", 1)),
        (-320, -400, ("▲ 20 %", 1)),  # процент — от модуля прошлого значения
        (30_000, 10, ("▲ 299 900 %", 1)),
    ],
)
def test_format_delta(current, previous, expected):
    assert format_delta(current, previous) == expected


def test_delta_color_follows_meaning_not_direction():
    t = THEMES["light"]
    assert delta_color(t, 1, lower_is_better=False) == t.good
    assert delta_color(t, -1, lower_is_better=False) == t.bad
    assert delta_color(t, 1, lower_is_better=True) == t.bad  # расходы выросли — плохо
    assert delta_color(t, -1, lower_is_better=True) == t.good
    assert delta_color(t, 0, lower_is_better=False) == t.ink_secondary


def test_bar_text_with_comparison():
    text = render_text({**BASE, "previous": [10, 8]}, kind="bar")
    assert text == (
        "a  ██████████  12  ▲ 20 %\n"
        "b  ██████▋      8   = 0 %\n"
        "▲▼ — изменение к «раньше»"
    )


def test_line_text_with_comparison_is_table():
    text = render_text({"labels": ["пн", "вт"], "values": [10, 15], "previous": [10, 12]}, kind="line")
    assert text == (
        "    сейчас  раньше\n"
        "пн      10      10   = 0 %\n"
        "вт      15      12  ▲ 25 %"
    )
