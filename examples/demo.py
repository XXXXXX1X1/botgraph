"""Рисует все графики в обеих темах в папку, чтобы посмотреть их глазами.

    python3 examples/demo.py out
"""

import sys
from datetime import date, timedelta
from pathlib import Path

from botgraf import render_png, render_text

_DAYS = [f"{d:02d}.10" for d in range(1, 15)]
_HABIT_START = date(2026, 5, 18)

# Имя файла → (kind, данные).
EXAMPLES = {
    "bar": ("bar", {"title": "Найдено на фото за день", "labels": ["Кошки", "Собаки", "Попугаи", "Хомяки"], "values": [12, 8, 3, 1]}),
    "bar-compare": ("bar", {
        "title": "Заказы по каналам",
        "labels": ["Telegram", "Сайт", "Звонки", "Авито"],
        "values": [124, 86, 31, 12],
        "previous": [103, 92, 31, 0],
        "previous_label": "прошлая неделя",
        "current_label": "эта неделя",
    }),
    "line": ("line", {
        "title": "Пользователи бота за 14 дней",
        "labels": _DAYS,
        "values": [120, 132, 128, 150, 171, 165, 190, 204, 198, 230, 241, 236, 265, 288],
    }),
    "line-compare": ("line", {
        "title": "Выручка: эта неделя против прошлой",
        "labels": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
        "values": [41000, 45500, 39800, 52000, 61000, 70500, 64000],
        "previous": [38000, 40200, 42100, 44000, 51000, 58000, 60500],
        "previous_label": "прошлая неделя",
        "current_label": "эта неделя",
    }),
    "pie": ("pie", {"title": "Расходы за сентябрь", "labels": ["Еда", "Транспорт", "Жильё", "Связь"], "values": [18400, 3200, 25000, 900]}),
    "calendar": ("calendar", {
        "title": "Тренировки с мая",
        "labels": [(_HABIT_START + timedelta(days=i)).isoformat() for i in range(150)],
        # Детерминированный «шум», чтобы картинка не менялась от запуска к запуску.
        "values": [0 if (i * 7 + i // 9) % 5 == 0 else (i * 37) % 60 + 10 for i in range(150)],
    }),
    "card": ("card", {
        "title": "Итоги 14 октября",
        "previous_label": "вчера",
        "metrics": [
            {"label": "Выручка", "value": 48200, "previous": 43000, "unit": "₽"},
            {"label": "Заказы", "value": 124, "previous": 131},
            {"label": "Средний чек", "value": 389, "previous": 328, "unit": "₽"},
            {"label": "Возвраты", "value": 3, "previous": 5, "lower_is_better": True},
        ],
        "trend": {
            "label": "Выручка за 14 дней",
            "labels": _DAYS,
            "values": [39000, 41000, 38500, 44000, 46000, 42000, 40500, 45000, 47000, 43500, 44800, 46900, 43000, 48200],
        },
    }),
}


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (kind, data) in EXAMPLES.items():
        for theme in ("light", "dark"):
            path = out_dir / f"{name}-{theme}.png"
            path.write_bytes(render_png(data, kind=kind, theme=theme).getvalue())
            print(path)
        print(render_text(data, kind=kind), end="\n\n")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "out"))
