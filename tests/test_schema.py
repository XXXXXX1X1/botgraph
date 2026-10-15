import json
import math
import re

import pytest

from botgraf import ChartError
from botgraf.schema import MAX_POINTS, validate

OK = {"title": "Кошки и собаки", "labels": ["Кошки", "Собаки"], "values": [12, 8]}


def test_valid_dict():
    chart = validate(OK, "bar")
    assert chart.title == "Кошки и собаки"
    assert chart.labels == ("Кошки", "Собаки")
    assert chart.values == (12.0, 8.0)


def test_valid_json_string_and_bytes():
    assert validate(json.dumps(OK), "bar") == validate(OK, "bar")
    assert validate(json.dumps(OK).encode(), "bar") == validate(OK, "bar")


def test_title_optional_and_blank_title_dropped():
    assert validate({"labels": ["a"], "values": [1]}, "bar").title is None
    assert validate({"title": "   ", "labels": ["a"], "values": [1]}, "bar").title is None


def test_long_label_and_title_are_shortened():
    chart = validate({"title": "З" * 100, "labels": ["П" * 50], "values": [1]}, "bar")
    assert len(chart.labels[0]) == 20 and chart.labels[0].endswith("…")
    assert len(chart.title) == 40 and chart.title.endswith("…")


def test_numpy_like_numbers_accepted():
    # Числа из numpy — наследники numbers.Real, их часто передают как есть.
    np = pytest.importorskip("numpy")
    assert validate({"labels": ["a"], "values": [np.int64(3)]}, "bar").values == (3.0,)


@pytest.mark.parametrize(
    ("data", "kind", "message"),
    [
        ("{нет", "bar", "некорректный JSON"),
        (b"\xc3\x28", "bar", "некорректный JSON"),  # bytes не в UTF-8, например cp1251
        ('{"labels": ["a"], "values": [' + "9" * 5000 + "]}", "bar", "некорректный JSON"),  # длиннее лимита int
        ([1, 2], "bar", "словарём"),
        ({"labels": ["a"]}, "bar", "нет обязательного поля values"),
        ({"labels": "a", "values": [1]}, "bar", "labels должен быть списком"),
        ({"labels": ["a"], "values": [1], "colour": "red"}, "bar", "неизвестные поля: colour"),
        ({"labels": ["a", "b"], "values": [1]}, "bar", "поровну"),
        ({"labels": [], "values": []}, "bar", "минимум 1"),
        ({"labels": ["a"], "values": [1]}, "line", "минимум 2"),
        ({"labels": ["a"], "values": ["12"]}, "bar", "values[0] должно быть числом"),
        ({"labels": ["a"], "values": [True]}, "bar", "values[0] должно быть числом"),
        ({"labels": ["a"], "values": [None]}, "bar", "values[0] должно быть числом"),
        ({"labels": ["a"], "values": [math.nan]}, "bar", "конечным"),
        ({"labels": ["a"], "values": [math.inf]}, "bar", "конечным"),
        ({"labels": ["a"], "values": [10**400]}, "bar", "слишком большое"),
        ({"labels": [1], "values": [1]}, "bar", "labels[0] должна быть строкой"),
        ({"labels": ["  "], "values": [1]}, "bar", "labels[0] пустая"),
        ({"title": 5, "labels": ["a"], "values": [1]}, "bar", "title должен быть строкой"),
        ({"labels": ["a", "b"], "values": [1, -1]}, "pie", "отрицательными"),
        ({"labels": ["a", "b"], "values": [0, 0]}, "pie", "больше нуля"),
        (OK, "scatter", "kind должен быть"),
    ],
)
def test_invalid_input(data, kind, message):
    with pytest.raises(ChartError, match=re.escape(message)):
        validate(data, kind)


@pytest.mark.parametrize("kind", ["bar", "line", "pie"])
def test_point_limit(kind):
    n = MAX_POINTS[kind]
    validate({"labels": [str(i) for i in range(n)], "values": [1] * n}, kind)
    with pytest.raises(ChartError, match=f"максимум {n}"):
        validate({"labels": [str(i) for i in range(n + 1)], "values": [1] * (n + 1)}, kind)


def test_chart_error_is_value_error():
    # Боты, которые уже ловят ValueError, обработают и ошибку БотГрафа.
    assert issubclass(ChartError, ValueError)
