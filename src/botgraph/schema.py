"""Функция 1: проверка и нормализация входных данных до рисования.

Здесь формат для bar, line, pie и calendar; у карточки дня свой формат (card.py),
но те же правила для чисел и строк. Общая точка входа — validate_payload (validator.py).
"""

import json
import math
import numbers
import re
from dataclasses import dataclass
from datetime import date

CHART_KINDS = ("bar", "line", "pie", "calendar")
KINDS = CHART_KINDS + ("card",)
# Сверх этих количеств график на экране телефона перестаёт читаться.
MAX_POINTS = {"bar": 12, "line": 31, "pie": 8, "calendar": 182}
MIN_PIE_SLICES = 2  # кольцо из одного куска ничего не сравнивает
CALENDAR_MAX_DAYS = 182  # 26 недель: шире клетки календаря на телефоне становятся слишком мелкими
MAX_LABEL_LEN = 20
MAX_TITLE_LEN = 50
_COMPARABLE = ("bar", "line")
_COMPARE_FIELDS = ("previous_label", "current_label", "lower_is_better")
_FIELDS = ("title", "labels", "values", "previous") + _COMPARE_FIELDS

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class BotGraphValidationError(ValueError):
    """Данные или параметры графика не подходят: code — для программы, field — где ошибка, message — что исправить."""

    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(code, message, field)
        self.code, self.message, self.field = code, message, field

    def __str__(self) -> str:
        where = f"Поле '{self.field}': " if self.field else ""
        return f"[{self.code}] {where}{self.message}"


@dataclass(frozen=True)
class ChartPayload:
    labels: tuple[str, ...]
    values: tuple[float, ...]
    title: str | None
    kind: str
    theme: str
    previous: tuple[float, ...] | None = None  # прошлый период для сравнения (bar, line)
    previous_label: str = "раньше"
    current_label: str = "сейчас"
    lower_is_better: bool = False  # например, расходы: рост — плохо
    dates: tuple[date, ...] | None = None  # только calendar

    def texts(self) -> list[tuple[str, str, bool]]:
        """Все строки, которые попадут на картинку: (поле, текст, жирный)."""
        texts = [(f"labels[{i}]", s, False) for i, s in enumerate(self.labels)]
        if self.title:
            texts.append(("title", self.title, True))
        if self.previous:
            texts += [("previous_label", self.previous_label, False), ("current_label", self.current_label, False)]
        return texts


def validate_chart(data, kind: str, theme: str) -> ChartPayload:
    data = as_dict(data)
    reject_unknown(data, _FIELDS)
    labels, values = required_list(data, "labels"), required_list(data, "values")
    if len(labels) != len(values):
        raise BotGraphValidationError(
            "LENGTH_MISMATCH", f"Количество подписей ({len(labels)}) не совпадает с количеством значений ({len(values)})",
            "values",
        )
    n = len(values)
    if n == 0:
        raise BotGraphValidationError("EMPTY_DATA", "Набор данных не может быть пустым", "labels")
    if kind == "pie" and n < MIN_PIE_SLICES:
        raise BotGraphValidationError(
            "INVALID_PIE_VALUES", f"Для круговой диаграммы нужно от {MIN_PIE_SLICES} до {MAX_POINTS['pie']} значений, "
            f"получено {n}", "values",
        )
    if n > MAX_POINTS[kind]:
        raise BotGraphValidationError(
            "TOO_MANY_ITEMS", f"Превышен лимит категорий для мобильного графика {kind}: максимум {MAX_POINTS[kind]}, "
            f"получено {n}", "labels",
        )

    clean_values = tuple(number(f"values[{i}]", v) for i, v in enumerate(values))
    negative = next((i for i, v in enumerate(clean_values) if v < 0), None)
    if kind == "pie" and negative is not None:
        raise BotGraphValidationError(
            "INVALID_PIE_VALUES", "Для круговой диаграммы значения не могут быть отрицательными", f"values[{negative}]",
        )
    if kind == "pie" and sum(clean_values) == 0:
        raise BotGraphValidationError("INVALID_PIE_VALUES", "Для круговой диаграммы сумма значений должна быть больше нуля",
                                      "values")
    if kind == "calendar" and negative is not None:
        raise BotGraphValidationError("NEGATIVE_VALUE", "Для calendar значения не могут быть отрицательными",
                                      f"values[{negative}]")

    return ChartPayload(
        labels=tuple(text(f"labels[{i}]", label, f"#{i + 1}") for i, label in enumerate(labels)),
        values=clean_values,
        title=optional_text("title", data.get("title"), MAX_TITLE_LEN),
        kind=kind,
        theme=theme,
        dates=_dates(labels) if kind == "calendar" else None,
        **_comparison(data, kind, n),
    )


def _comparison(data: dict, kind: str, n: int) -> dict:
    if "previous" not in data:
        extra = [key for key in _COMPARE_FIELDS if key in data]
        if extra:
            raise BotGraphValidationError("MISSING_KEY", f"Поле {extra[0]} задаётся только вместе с previous", "previous")
        return {}
    if kind not in _COMPARABLE:
        raise BotGraphValidationError(
            "UNSUPPORTED_COMPARISON", f"Сравнение с прошлым периодом есть только для {' и '.join(_COMPARABLE)}", "previous",
        )
    previous = required_list(data, "previous")
    if len(previous) != n:
        raise BotGraphValidationError(
            "LENGTH_MISMATCH", f"В previous {len(previous)} значений, а в values {n} — должно быть поровну", "previous",
        )
    result = {"previous": tuple(number(f"previous[{i}]", v) for i, v in enumerate(previous))}
    for key, default in (("previous_label", "раньше"), ("current_label", "сейчас")):
        if key in data:
            result[key] = text(key, data[key], default)
    if "lower_is_better" in data:
        result["lower_is_better"] = flag("lower_is_better", data["lower_is_better"])
    return result


def _dates(labels) -> tuple[date, ...]:
    dates = []
    for i, label in enumerate(labels):
        try:
            day = date.fromisoformat(label.strip())
        except ValueError:
            raise BotGraphValidationError(
                "INVALID_DATE", f"Для calendar нужна дата в формате ГГГГ-ММ-ДД, получено {label!r}", f"labels[{i}]",
            ) from None
        if day in dates:
            raise BotGraphValidationError("INVALID_DATE", f"Дата {label.strip()} повторяется", f"labels[{i}]")
        dates.append(day)
    span = (max(dates) - min(dates)).days + 1
    if span > CALENDAR_MAX_DAYS:
        raise BotGraphValidationError(
            "INVALID_DATE", f"Даты должны укладываться в {CALENDAR_MAX_DAYS} дн., сейчас {span}", "labels",
        )
    return tuple(dates)


# Общие проверки — ими пользуется и карточка дня. path — где в данных поле, для текста ошибки.


def as_dict(data) -> dict:
    """Верхний уровень данных: словарь или строка JSON."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            raise BotGraphValidationError(
                "INVALID_JSON", f"Некорректный JSON: {e.msg} (строка {e.lineno}, столбец {e.colno})", "data",
            ) from None
        except ValueError as e:  # bytes не в UTF-8 или число длиннее лимита int в Python
            raise BotGraphValidationError("INVALID_JSON", f"Некорректный JSON: {e}", "data") from None
    if not isinstance(data, dict):
        raise BotGraphValidationError(
            "INVALID_JSON", "Входные данные должны быть словарём или корректной JSON-строкой объекта", "data",
        )
    return data


def reject_unknown(data: dict, allowed, path: str = "") -> None:
    unknown = sorted(str(k) for k in data if k not in allowed)
    if unknown:
        raise BotGraphValidationError(
            "UNKNOWN_FIELD", f"Неизвестные поля: {', '.join(unknown)}; допустимы: {', '.join(allowed)}",
            f"{path}.{unknown[0]}" if path else unknown[0],
        )


def required_list(data: dict, key: str, path: str = "") -> list:
    full = f"{path}.{key}" if path else key
    if key not in data:
        raise BotGraphValidationError("MISSING_KEY", "Отсутствует обязательное поле", full)
    if not isinstance(data[key], (list, tuple)):
        raise BotGraphValidationError("INVALID_TYPE", f"Ожидается список, получено {_show(data[key])}", full)
    return data[key]


def number(path: str, v) -> float:
    """Конечное число (bool — не число, хоть и наследник int)."""
    if not isinstance(v, bool) and isinstance(v, numbers.Real):
        try:
            f = float(v)
        except OverflowError:
            f = math.inf
        if math.isfinite(f):
            return f
    raise BotGraphValidationError("INVALID_VALUE_TYPE", f"Ожидается конечное число, получено {_show(v)}", path)


def clean(s: str) -> str:
    """Управляющие символы — в пробел, пробелы по краям и повторы — прочь."""
    return " ".join(_CONTROL.sub(" ", s).split())


def text(path: str, s, default: str | None, limit: int = MAX_LABEL_LEN) -> str | None:
    """Подпись: строка; пустая после очистки — default, длинная обрезается с «…»."""
    if not isinstance(s, str):
        raise BotGraphValidationError("INVALID_TYPE", f"Ожидается строка, получено {_show(s)}", path)
    return shorten(clean(s), limit) or default


def optional_text(path: str, s, limit: int) -> str | None:
    """Заголовок: необязательный, пустой считается отсутствующим."""
    return None if s is None else text(path, s, None, limit)


def flag(path: str, v) -> bool:
    if not isinstance(v, bool):
        raise BotGraphValidationError("INVALID_TYPE", f"Ожидается true или false, получено {_show(v)}", path)
    return v


def shorten(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _show(v) -> str:
    """Значение в тексте ошибки: число из 5000 цифр целиком не нужно."""
    return shorten(repr(v), 40)
