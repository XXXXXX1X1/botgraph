"""Функция 1: проверка входных данных до рисования.

Здесь формат для bar, line, pie и calendar; у карточки дня свой формат (card.py),
но те же правила для чисел и строк.
"""

import json
import math
import numbers
from dataclasses import dataclass
from datetime import date

CHART_KINDS = ("bar", "line", "pie", "calendar")
KINDS = CHART_KINDS + ("card",)
# Сверх этих количеств график на экране телефона перестаёт читаться.
MIN_POINTS = {"bar": 1, "line": 2, "pie": 1, "calendar": 1}
MAX_POINTS = {"bar": 12, "line": 31, "pie": 6, "calendar": 182}
CALENDAR_MAX_DAYS = 182  # 26 недель: шире клетки календаря на телефоне становятся слишком мелкими
MAX_LABEL_LEN = 20
MAX_TITLE_LEN = 40
_COMPARABLE = ("bar", "line")
_COMPARE_FIELDS = ("previous_label", "current_label", "lower_is_better")
_FIELDS = ("title", "labels", "values", "previous") + _COMPARE_FIELDS


class ChartError(ValueError):
    """Данные или параметры графика не подходят. Текст объясняет, что исправить."""


@dataclass(frozen=True)
class ChartData:
    title: str | None
    labels: tuple[str, ...]
    values: tuple[float, ...]
    previous: tuple[float, ...] | None = None  # прошлый период для сравнения (bar, line)
    previous_label: str = "раньше"
    current_label: str = "сейчас"
    lower_is_better: bool = False  # например, расходы: рост — плохо
    dates: tuple[date, ...] | None = None  # только calendar

    def texts(self) -> list[tuple[str, str, bool]]:
        """Все строки, которые попадут на картинку: (поле, текст, жирный)."""
        texts = [("labels", s, False) for s in self.labels]
        if self.title:
            texts.append(("title", self.title, True))
        if self.previous:
            texts += [("previous_label", self.previous_label, False), ("current_label", self.current_label, False)]
        return texts


def check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ChartError(f"kind должен быть одним из: {', '.join(KINDS)}; получено {kind!r}")


def validate(data, kind: str) -> ChartData:
    if kind not in CHART_KINDS:
        raise ChartError(f"kind должен быть одним из: {', '.join(CHART_KINDS)}; получено {kind!r}")
    data = as_dict(data)
    reject_unknown(data, _FIELDS)
    labels, values = required_list(data, "labels"), required_list(data, "values")
    if len(labels) != len(values):
        raise ChartError(f"в labels {len(labels)} элементов, а в values {len(values)} — должно быть поровну")
    n = len(values)
    if n < MIN_POINTS[kind]:
        raise ChartError(f"для {kind} нужно минимум {MIN_POINTS[kind]} знач., получено {n}")
    if n > MAX_POINTS[kind]:
        raise ChartError(f"для {kind} допустимо максимум {MAX_POINTS[kind]} знач., получено {n}")

    clean_values = tuple(number(f"values[{i}]", v) for i, v in enumerate(values))
    if kind in ("pie", "calendar") and any(v < 0 for v in clean_values):
        raise ChartError(f"для {kind} значения не могут быть отрицательными")
    if kind == "pie" and sum(clean_values) == 0:
        raise ChartError("для pie сумма значений должна быть больше нуля")

    compare = _comparison(data, kind, n)
    return ChartData(
        title=optional_text("title", data.get("title"), MAX_TITLE_LEN),
        labels=tuple(text(f"labels[{i}]", label) for i, label in enumerate(labels)),
        values=clean_values,
        dates=_dates(labels) if kind == "calendar" else None,
        **compare,
    )


def _comparison(data: dict, kind: str, n: int) -> dict:
    if "previous" not in data:
        extra = [key for key in _COMPARE_FIELDS if key in data]
        if extra:
            raise ChartError(f"поле {extra[0]} нужно только вместе с previous")
        return {}
    if kind not in _COMPARABLE:
        raise ChartError(f"previous поддерживается только для {' и '.join(_COMPARABLE)}")
    previous = required_list(data, "previous")
    if len(previous) != n:
        raise ChartError(f"в previous {len(previous)} элементов, а в values {n} — должно быть поровну")
    result = {"previous": tuple(number(f"previous[{i}]", v) for i, v in enumerate(previous))}
    for key in ("previous_label", "current_label"):
        if key in data:
            result[key] = text(key, data[key])
    if "lower_is_better" in data:
        result["lower_is_better"] = flag("lower_is_better", data["lower_is_better"])
    return result


def _dates(labels) -> tuple[date, ...]:
    dates = []
    for i, label in enumerate(labels):
        try:
            dates.append(date.fromisoformat(label.strip()))
        except ValueError:
            raise ChartError(f"labels[{i}]: для calendar нужна дата в формате ГГГГ-ММ-ДД, получено {label!r}") from None
    if len(set(dates)) != len(dates):
        raise ChartError("для calendar даты в labels не должны повторяться")
    span = (max(dates) - min(dates)).days + 1
    if span > CALENDAR_MAX_DAYS:
        raise ChartError(f"для calendar даты должны укладываться в {CALENDAR_MAX_DAYS} дн., сейчас {span}")
    return tuple(dates)


# Общие проверки — ими пользуется и карточка дня. path — где в данных поле, для текста ошибки.


def as_dict(data) -> dict:
    """Верхний уровень данных: словарь или строка JSON."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            raise ChartError(f"некорректный JSON: {e.msg} (строка {e.lineno}, столбец {e.colno})") from None
        except ValueError as e:  # bytes не в UTF-8 или число длиннее лимита int в Python
            raise ChartError(f"некорректный JSON: {e}") from None
    if not isinstance(data, dict):
        raise ChartError("данные должны быть словарём или JSON-объектом")
    return data


def reject_unknown(data: dict, allowed, path: str = "") -> None:
    unknown = sorted(str(k) for k in data if k not in allowed)
    if unknown:
        where = f" в {path}" if path else ""
        raise ChartError(f"неизвестные поля{where}: {', '.join(unknown)}; допустимы {', '.join(allowed)}")


def required_list(data: dict, key: str, path: str = "") -> list:
    full = f"{path}.{key}" if path else key
    if key not in data:
        raise ChartError(f"нет обязательного поля {full}")
    if not isinstance(data[key], (list, tuple)):
        raise ChartError(f"{full} должен быть списком")
    return data[key]


def number(path: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, numbers.Real):
        raise ChartError(f"{path} должно быть числом, получено {v!r}")
    try:
        f = float(v)
    except OverflowError:
        raise ChartError(f"{path}: слишком большое число") from None
    if not math.isfinite(f):
        raise ChartError(f"{path} должно быть конечным числом, получено {v}")
    return f


def text(path: str, s, limit: int = MAX_LABEL_LEN) -> str:
    """Подпись: непустая строка, длинная обрезается с «…»."""
    if not isinstance(s, str):
        raise ChartError(f"{path} должна быть строкой, получено {s!r}")
    s = s.strip()
    if not s:
        raise ChartError(f"{path} пустая")
    return shorten(s, limit)


def optional_text(path: str, s, limit: int) -> str | None:
    """Заголовок: необязательный, пустой считается отсутствующим."""
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    if not isinstance(s, str):
        raise ChartError(f"{path} должен быть строкой, получено {s!r}")
    return shorten(s.strip(), limit)


def flag(path: str, v) -> bool:
    if not isinstance(v, bool):
        raise ChartError(f"{path} должно быть true или false, получено {v!r}")
    return v


def shorten(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"
