"""Карточка дня."""

import json

import pytest

from botgraph import BotGraphValidationError, render_text, validate_payload
from botgraph.card import Metric
from botgraph.fmt import sparkline

METRIC = {"label": "Выручка", "value": 48000, "previous": 40000, "unit": "₽"}


def test_card_parsed_with_defaults():
    card = validate_payload(json.dumps({"metrics": [METRIC, {"label": "Заказы", "value": 12}]}), "card", "dark")
    assert (card.kind, card.theme) == ("card", "dark")
    assert card.title is None and card.previous_label == "вчера" and card.trend is None
    assert card.metrics == (Metric("Выручка", 48000.0, 40000.0, "₽"), Metric("Заказы", 12.0))


def test_trend_is_validated_as_line():
    card = validate_payload({"metrics": [METRIC], "trend": {"label": "Неделя", "labels": ["a", "b"], "values": [1, 2]}}, "card")
    assert (card.trend.title, card.trend.labels, card.trend.values) == ("Неделя", ("a", "b"), (1.0, 2.0))


@pytest.mark.parametrize(
    ("data", "code", "field"),
    [
        ({}, "MISSING_KEY", "metrics"),
        ({"metrics": []}, "EMPTY_DATA", "metrics"),
        ({"metrics": [METRIC] * 5}, "TOO_MANY_ITEMS", "metrics"),
        ({"metrics": [5]}, "INVALID_TYPE", "metrics[0]"),
        ({"metrics": [{"label": "a"}]}, "MISSING_KEY", "metrics[0].value"),
        ({"metrics": [{"label": "a", "value": "1"}]}, "INVALID_VALUE_TYPE", "metrics[0].value"),
        ({"metrics": [{"label": "a", "value": 1, "colour": 1}]}, "UNKNOWN_FIELD", "metrics[0].colour"),
        ({"metrics": [{"label": "a", "value": 1, "lower_is_better": 1}]}, "INVALID_TYPE", "metrics[0].lower_is_better"),
        ({"metrics": [METRIC], "title": 1}, "INVALID_TYPE", "title"),
        ({"metrics": [METRIC], "values": [1]}, "UNKNOWN_FIELD", "values"),
        ({"metrics": [METRIC], "trend": [1, 2]}, "INVALID_TYPE", "trend"),
        ({"metrics": [METRIC], "trend": {"labels": ["a"], "values": [1]}}, "TOO_FEW_ITEMS", "trend.values"),
        ({"metrics": [METRIC], "trend": {"labels": ["a", "b"], "values": [1, "x"]}}, "INVALID_VALUE_TYPE", "trend.values[1]"),
        ({"metrics": [METRIC], "trend": {"labels": ["a", "b"], "values": [1, 2], "title": "x"}}, "UNKNOWN_FIELD", "trend.title"),
        ({"metrics": [METRIC], "trend": {"label": 5, "labels": ["a", "b"], "values": [1, 2]}}, "INVALID_TYPE", "trend.label"),
    ],
)
def test_invalid_card(data, code, field):
    with pytest.raises(BotGraphValidationError) as e:
        validate_payload(data, "card")
    assert (e.value.code, e.value.field) == (code, field)


def test_empty_metric_label_gets_number():
    card = validate_payload({"metrics": [METRIC, {"label": " ", "value": 1, "unit": "\t"}]}, "card")
    assert (card.metrics[1].label, card.metrics[1].unit) == ("#2", None)


def test_long_unit_is_shortened():
    assert validate_payload({"metrics": [{"label": "a", "value": 1, "unit": "километров"}]}, "card").metrics[0].unit == "килом…"


def test_card_text():
    data = {
        "title": "Итоги дня",
        "metrics": [METRIC, {"label": "Заказы", "value": 12}],
        "trend": {"labels": ["a", "b", "c"], "values": [1, 2, 3]},
    }
    assert render_text(data, kind="card") == (
        "Итоги дня\n"
        "Выручка  48 000 ₽  ▲ 20 %\n"
        "Заказы         12\n"
        "▲▼ — изменение к «вчера»\n"
        "\n"
        "Динамика\n"
        "▁▅█  3"
    )


def test_card_text_without_previous_has_no_note():
    assert render_text({"metrics": [{"label": "Заказы", "value": 12}]}, kind="card") == "Заказы  12"


def test_sparkline():
    assert sparkline([1, 2, 3]) == "▁▅█"
    assert sparkline([5, 5]) == "▄▄"  # ровный ряд — посередине, а не «на нуле»
