import json
import math
import pickle

import pytest

from botgraph import BotGraphValidationError, ChartPayload, validate_payload
from botgraph.schema import MAX_POINTS

OK = {"title": "Кошки и собаки", "labels": ["Кошки", "Собаки"], "values": [12, 8]}


def test_valid_dict():
    chart = validate_payload(OK)
    assert chart == ChartPayload(labels=("Кошки", "Собаки"), values=(12.0, 8.0), title="Кошки и собаки",
                                 kind="bar", theme="light")


def test_kind_and_theme_are_kept():
    chart = validate_payload(OK, kind="pie", theme="dark")
    assert (chart.kind, chart.theme) == ("pie", "dark")


def test_valid_json_string_and_bytes():
    assert validate_payload(json.dumps(OK)) == validate_payload(OK)
    assert validate_payload(json.dumps(OK).encode()) == validate_payload(OK)


def test_title_optional_and_blank_title_dropped():
    assert validate_payload({"labels": ["a"], "values": [1]}).title is None
    assert validate_payload({"title": "   ", "labels": ["a"], "values": [1]}).title is None


def test_long_label_and_title_are_shortened():
    chart = validate_payload({"title": "З" * 150, "labels": ["П" * 50], "values": [1]})
    assert chart.labels[0] == "П" * 19 + "…"
    assert chart.title == "З" * 49 + "…"


def test_text_is_normalized():
    chart = validate_payload({"title": " Итоги\nдня ", "labels": ["Кошки\t🐱", "  ", "a\x00b"], "values": [1, 2, 3]})
    assert chart.title == "Итоги дня"
    assert chart.labels == ("Кошки 🐱", "#2", "a b")


def test_big_numbers_accepted():
    assert validate_payload({"labels": ["a", "b"], "values": [1.5e12, -10**15]}).values == (1.5e12, -1e15)


def test_numpy_like_numbers_accepted():
    # Числа из numpy — наследники numbers.Real, их часто передают как есть.
    np = pytest.importorskip("numpy")
    assert validate_payload({"labels": ["a"], "values": [np.int64(3)]}).values == (3.0,)


@pytest.mark.parametrize(
    ("data", "kind", "theme", "code", "field"),
    [
        ("{нет", "bar", "light", "INVALID_JSON", "data"),
        (b"\xc3\x28", "bar", "light", "INVALID_JSON", "data"),  # bytes не в UTF-8, например cp1251
        ('{"labels": ["a"], "values": [' + "9" * 5000 + "]}", "bar", "light", "INVALID_JSON", "data"),  # длиннее лимита int
        ([1, 2], "bar", "light", "INVALID_JSON", "data"),
        ({"labels": ["a"]}, "bar", "light", "MISSING_KEY", "values"),
        ({"values": [1]}, "bar", "light", "MISSING_KEY", "labels"),
        ({"labels": "a", "values": [1]}, "bar", "light", "INVALID_TYPE", "labels"),
        ({"labels": ["a"], "values": [1], "colour": "red"}, "bar", "light", "UNKNOWN_FIELD", "colour"),
        ({"labels": ["a", "b"], "values": [1]}, "bar", "light", "LENGTH_MISMATCH", "values"),
        ({"labels": [], "values": []}, "bar", "light", "EMPTY_DATA", "labels"),
        ({"labels": [], "values": []}, "pie", "light", "EMPTY_DATA", "labels"),
        ({"labels": ["a"], "values": ["много"]}, "bar", "light", "INVALID_VALUE_TYPE", "values[0]"),
        ({"labels": ["a"], "values": [True]}, "bar", "light", "INVALID_VALUE_TYPE", "values[0]"),
        ({"labels": ["a"], "values": [None]}, "bar", "light", "INVALID_VALUE_TYPE", "values[0]"),
        ({"labels": ["a"], "values": [math.nan]}, "bar", "light", "INVALID_VALUE_TYPE", "values[0]"),
        ({"labels": ["a"], "values": [math.inf]}, "bar", "light", "INVALID_VALUE_TYPE", "values[0]"),
        ({"labels": ["a", "b"], "values": [1, 10**400]}, "bar", "light", "INVALID_VALUE_TYPE", "values[1]"),
        ({"labels": [1], "values": [1]}, "bar", "light", "INVALID_TYPE", "labels[0]"),
        ({"title": 5, "labels": ["a"], "values": [1]}, "bar", "light", "INVALID_TYPE", "title"),
        ({"labels": ["a"], "values": [1]}, "pie", "light", "INVALID_PIE_VALUES", "values"),
        ({"labels": ["a", "b"], "values": [1, -1]}, "pie", "light", "INVALID_PIE_VALUES", "values[1]"),
        ({"labels": ["a", "b"], "values": [0, 0]}, "pie", "light", "INVALID_PIE_VALUES", "values"),
        (OK, "scatter", "light", "UNSUPPORTED_KIND", "kind"),
        (OK, "bar", "blue", "UNSUPPORTED_THEME", "theme"),
        (OK, "bar", ["dark"], "UNSUPPORTED_THEME", "theme"),
    ],
)
def test_invalid_input(data, kind, theme, code, field):
    with pytest.raises(BotGraphValidationError) as e:
        validate_payload(data, kind, theme)
    assert (e.value.code, e.value.field) == (code, field)
    assert str(e.value) == f"[{code}] Поле '{field}': {e.value.message}"


def test_error_text_explains_the_fix():
    with pytest.raises(BotGraphValidationError) as e:
        validate_payload({"labels": ["Кошки", "Собаки"], "values": [12]})
    assert str(e.value) == ("[LENGTH_MISMATCH] Поле 'values': "
                            "Количество подписей (2) не совпадает с количеством значений (1)")


def test_huge_number_is_shortened_in_message():
    with pytest.raises(BotGraphValidationError) as e:
        validate_payload({"labels": ["a"], "values": [10**400]})
    assert len(e.value.message) < 120


@pytest.mark.parametrize("kind", ["bar", "line", "pie"])
def test_point_limit(kind):
    n = MAX_POINTS[kind]
    validate_payload({"labels": [str(i) for i in range(n)], "values": [1] * n}, kind)
    with pytest.raises(BotGraphValidationError) as e:
        validate_payload({"labels": [str(i) for i in range(n + 1)], "values": [1] * (n + 1)}, kind)
    assert (e.value.code, e.value.field) == ("TOO_MANY_ITEMS", "labels") and f"максимум {n}" in e.value.message


def test_limits_for_phone_screen():
    assert (MAX_POINTS["bar"], MAX_POINTS["pie"]) == (12, 8)
    assert MAX_POINTS["line"] >= 12  # месяц по дням тоже читается
    validate_payload({"labels": ["a"], "values": [1]}, "line")  # одна точка — уже линия


def test_error_is_value_error_and_pickles():
    # Боты, которые уже ловят ValueError, обработают и ошибку БотГрафа; пул процессов передаст её целиком.
    assert issubclass(BotGraphValidationError, ValueError)
    e = pickle.loads(pickle.dumps(BotGraphValidationError("EMPTY_DATA", "пусто", "labels")))
    assert (e.code, e.message, e.field) == ("EMPTY_DATA", "пусто", "labels")


def test_error_without_field():
    assert str(BotGraphValidationError("X", "сообщение")) == "[X] сообщение"
