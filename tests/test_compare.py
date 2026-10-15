"""Сравнение с прошлым периодом: столбики с меткой «было» и две линии."""

import re

import pytest

from botgraf import ChartError, render_text
from botgraf.fmt import format_delta
from botgraf.schema import validate
from botgraf.themes import THEMES, delta_color

BASE = {"labels": ["a", "b"], "values": [12, 8]}


def test_previous_fields_parsed_with_defaults():
    chart = validate({**BASE, "previous": [10, 8]}, "bar")
    assert chart.previous == (10.0, 8.0)
    assert (chart.previous_label, chart.current_label, chart.lower_is_better) == ("раньше", "сейчас", False)
    chart = validate({**BASE, "previous": [10, 8], "previous_label": " вчера ", "lower_is_better": True}, "line")
    assert (chart.previous_label, chart.lower_is_better) == ("вчера", True)


@pytest.mark.parametrize(
    ("data", "kind", "message"),
    [
        ({**BASE, "previous": [1]}, "bar", "в previous 1 элементов, а в values 2"),
        ({**BASE, "previous": [1, "2"]}, "bar", "previous[1] должно быть числом"),
        ({**BASE, "previous": 5}, "bar", "previous должен быть списком"),
        ({**BASE, "previous": [1, 2]}, "pie", "previous поддерживается только для bar и line"),
        ({**BASE, "previous_label": "вчера"}, "bar", "поле previous_label нужно только вместе с previous"),
        ({**BASE, "previous": [1, 2], "lower_is_better": "да"}, "bar", "lower_is_better должно быть true или false"),
        ({**BASE, "previous": [1, 2], "current_label": ""}, "bar", "current_label пустая"),
    ],
)
def test_invalid_comparison(data, kind, message):
    with pytest.raises(ChartError, match=re.escape(message)):
        validate(data, kind)


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
