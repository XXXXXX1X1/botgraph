import pytest

from botgraf import ChartError, render_text
from botgraf.fmt import format_percent, format_value


def test_bar_text():
    text = render_text({"title": "За день", "labels": ["Кошки", "Собаки"], "values": [12, 8]}, kind="bar")
    assert text == (
        "За день\n"
        "Кошки   ██████████  12\n"
        "Собаки  ██████▋      8"
    )


def test_bar_text_negative_uses_length_by_magnitude():
    text = render_text({"labels": ["Доход", "Расход"], "values": [50, -100]})
    assert text.splitlines()[1] == "Расход  ██████████  −100"


def test_bar_text_all_zero():
    assert render_text({"labels": ["a"], "values": [0]}) == "a              0"


def test_line_text_is_plain_list():
    text = render_text({"labels": ["пн", "вт"], "values": [3, 12.5]}, kind="line")
    assert text == "пн     3\nвт  12,5"


def test_pie_text_with_percent_and_total():
    text = render_text({"labels": ["Еда", "Жильё"], "values": [25, 75]}, kind="pie")
    assert text == "Еда    25  25 %\nЖильё  75  75 %\nВсего: 100"


def test_text_uses_same_validation():
    with pytest.raises(ChartError):
        render_text({"labels": ["a", "b"], "values": [1]})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (12, "12"),
        (3.14159, "3,14"),
        (-0.001, "0"),
        (12345, "12 345"),
        (-61000, "−61 000"),
        (999_999, "999 999"),
        (1_500_000, "1,5 млн"),
        (2e9, "2 млрд"),
        (1.1e12, "1,1 трлн"),
    ],
)
def test_format_value(value, expected):
    assert format_value(value) == expected


def test_format_percent():
    assert format_percent(1, 4) == "25 %"
    assert format_percent(1, 1000) == "<1 %"
    assert format_percent(0, 10) == "0 %"
