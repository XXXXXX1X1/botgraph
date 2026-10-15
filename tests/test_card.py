"""Карточка дня."""

import json
import re

import pytest

from botgraf import ChartError, render_text
from botgraf.card import MAX_METRICS, Metric, validate_card
from botgraf.fmt import sparkline

METRIC = {"label": "Выручка", "value": 48000, "previous": 40000, "unit": "₽"}


def test_card_parsed_with_defaults():
    card = validate_card(json.dumps({"metrics": [METRIC, {"label": "Заказы", "value": 12}]}))
    assert card.title is None and card.previous_label == "вчера" and card.trend is None
    assert card.metrics == (Metric("Выручка", 48000.0, 40000.0, "₽"), Metric("Заказы", 12.0))


def test_trend_is_validated_as_line():
    card = validate_card({"metrics": [METRIC], "trend": {"label": "Неделя", "labels": ["a", "b"], "values": [1, 2]}})
    assert (card.trend.title, card.trend.labels, card.trend.values) == ("Неделя", ("a", "b"), (1.0, 2.0))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({}, "нет обязательного поля metrics"),
        ({"metrics": []}, f"для card нужно от 1 до {MAX_METRICS} метрик в metrics, получено 0"),
        ({"metrics": [METRIC] * 5}, "получено 5"),
        ({"metrics": [5]}, "metrics[0] должен быть словарём"),
        ({"metrics": [{"label": "a"}]}, "нет обязательного поля metrics[0].value"),
        ({"metrics": [{"label": "a", "value": "1"}]}, "metrics[0].value должно быть числом"),
        ({"metrics": [{"label": "a", "value": 1, "colour": 1}]}, "неизвестные поля в metrics[0]: colour"),
        ({"metrics": [{"label": "a", "value": 1, "lower_is_better": 1}]}, "metrics[0].lower_is_better должно быть true или false"),
        ({"metrics": [METRIC], "title": 1}, "title должен быть строкой"),
        ({"metrics": [METRIC], "values": [1]}, "неизвестные поля: values"),
        ({"metrics": [METRIC], "trend": [1, 2]}, "trend должен быть словарём"),
        ({"metrics": [METRIC], "trend": {"labels": ["a"], "values": [1]}}, "trend: для line нужно минимум 2"),
        ({"metrics": [METRIC], "trend": {"labels": ["a", "b"], "values": [1, 2], "title": "x"}}, "неизвестные поля в trend: title"),
        ({"metrics": [METRIC], "trend": {"label": 5, "labels": ["a", "b"], "values": [1, 2]}}, "trend.label должен быть строкой"),
    ],
)
def test_invalid_card(data, message):
    with pytest.raises(ChartError, match=re.escape(message)):
        validate_card(data)


def test_long_unit_is_shortened():
    assert validate_card({"metrics": [{"label": "a", "value": 1, "unit": "километров"}]}).metrics[0].unit == "килом…"


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
