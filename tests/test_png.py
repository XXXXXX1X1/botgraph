import gc
import re
import threading
import tracemalloc

import matplotlib.pyplot as plt
import pytest
from matplotlib.figure import Figure
from matplotlib.image import imread

from botgraf import ChartError, render_png
from botgraf.png import _bar, _bar_xlim
from botgraf.schema import MAX_POINTS, validate
from botgraf.themes import DPI, THEMES, WIDTH_PX, fit_width, text_width_px

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SAMPLES = {
    "bar": {"title": "Найдено на фото", "labels": ["Кошки", "Собаки"], "values": [12, 8]},
    "line": {"title": "Пользователи", "labels": ["пн", "вт", "ср"], "values": [3, 5, 4]},
    "pie": {"title": "Расходы", "labels": ["Еда", "Жильё"], "values": [18400, 25000]},
    "calendar": {"title": "Тренировки", "labels": ["2026-10-12", "2026-10-14"], "values": [1, 3]},
    "card": {"title": "Итоги дня", "metrics": [{"label": "Выручка", "value": 48000, "previous": 43000, "unit": "₽"}]},
}


def _size(buf) -> tuple[int, int]:
    height, width = imread(buf).shape[:2]
    buf.seek(0)
    return width, height


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("kind", SAMPLES)
def test_png_ready_to_send(kind, theme):
    buf = render_png(SAMPLES[kind], kind=kind, theme=theme)
    assert buf.tell() == 0
    assert buf.read(8) == PNG_SIGNATURE
    buf.seek(0)
    assert _size(buf)[0] == 1080
    assert buf.name.endswith(".png")


def test_themes_differ():
    light = render_png(SAMPLES["bar"], theme="light").getvalue()
    dark = render_png(SAMPLES["bar"], theme="dark").getvalue()
    assert light != dark


@pytest.mark.parametrize(
    ("kind", "data"),
    [
        ("bar", {"title": "Т" * 40, "labels": ["Д" * 20] * MAX_POINTS["bar"], "values": [1.1e12] * 12}),
        ("bar", {"labels": ["Доход", "Расход"], "values": [52000, -61000]}),
        ("bar", {"labels": ["ноль"], "values": [0]}),
        ("line", {"labels": [f"{d} октября 2026" for d in range(1, 32)], "values": [d % 7 - 3 for d in range(31)]}),
        ("line", {"labels": ["пн", "вт"], "values": [5, 5]}),
        ("pie", {"labels": ["П" * 20] * MAX_POINTS["pie"], "values": [1e9, 1, 0, 0, 0, 3]}),
        ("bar", {"labels": ["Ш" * 20, "Ж" * 20], "values": [-999.9e9, 888.8e9]}),
        ("line", {"labels": ["Ш" * 20, "Ж" * 20], "values": [1, 2]}),
        ("bar", {"labels": ["Ш" * 20, "б"], "values": [1e9, -2], "previous": [-2e9, 0],
                 "previous_label": "Ш" * 20, "current_label": "Щ" * 20}),
        ("line", {"labels": ["пн", "вт"], "values": [5, 5], "previous": [5, 5]}),
        ("line", {"labels": [str(d) for d in range(31)], "values": [0] * 31, "previous": [-1e12] * 31}),
        ("calendar", {"labels": ["2026-10-14"], "values": [0]}),
        ("calendar", {"labels": [f"2026-{m:02d}-01" for m in (1, 6)], "values": [5, 1e9]}),
        ("card", {"metrics": [{"label": "Ш" * 20, "value": -1.1e12, "previous": 0, "unit": "Ш" * 6}] * 4,
                  "trend": {"label": "Ш" * 40, "labels": ["Ш" * 20] * 31, "values": [1] * 31}}),
        ("card", {"metrics": [{"label": "один", "value": 0}]}),
    ],
)
def test_extreme_data_renders(kind, data):
    # pytest превращает предупреждения в ошибки: так ловится и недостающий глиф.
    assert _size(render_png(data, kind=kind))[0] == 1080


def test_bar_axis_never_inverts_on_wide_labels_and_values():
    # Широкие буквы и длинные значения раньше давали отрицательный запас — ось переворачивалась.
    for frac in (0.1, 0.5, 0.9, 2.0):
        lo, hi = _bar_xlim(-999.9e9, 888.8e9, frac, 1)  # запас только справа, под подписи
        assert lo == -999.9e9 and 888.8e9 < hi < float("inf")
        lo, hi = _bar_xlim(-999.9e9, 0, frac, -1)
        assert -float("inf") < lo < -999.9e9 and hi == 0


def test_bar_mixed_signs_keeps_category_names():
    # Подписи по обе стороны нуля раньше съедали ширину — названия сжимались до «М…».
    chart = validate({"labels": ["Москва", "Казань", "Сочи"], "values": [-12000, 45000, 8000],
                      "previous": [-5000, 30000, 9000]}, "bar")
    fig = Figure(figsize=(WIDTH_PX / DPI, 6), dpi=DPI, layout="constrained")
    _bar(fig, chart, THEMES["light"])
    ax = fig.axes[0]
    assert [t.get_text() for t in ax.get_yticklabels()] == ["Москва", "Казань", "Сочи"]
    assert all(a.xy[0] >= 0 and a.get_ha() == "left" for a in ax.texts)  # все подписи справа от нуля


def test_fit_width_shortens_by_pixels_not_chars():
    narrow, wide = "i" * 20, "Ш" * 20
    assert fit_width(narrow, 15, 400) == narrow
    fitted = fit_width(wide, 15, 400)
    assert fitted.endswith("…") and text_width_px(fitted, 15) <= 400


def test_unsupported_glyph_is_clear_error():
    # Иероглифа нет в DejaVu Sans: вместо квадратика на картинке — понятная ошибка.
    with pytest.raises(ChartError, match="символ '猫' не поддерживается шрифтом"):
        render_png({"labels": ["Кошки 猫"], "values": [1]})
    with pytest.raises(ChartError, match="title"):
        render_png({"title": "猫", "labels": ["a"], "values": [1]})
    with pytest.raises(ChartError, match="previous_label"):
        render_png({"labels": ["a"], "values": [1], "previous": [1], "previous_label": "猫"})
    with pytest.raises(ChartError, match=re.escape("metrics[0].label")):
        render_png({"metrics": [{"label": "猫", "value": 1}]}, kind="card")
    with pytest.raises(ChartError, match=re.escape("trend.labels")):
        render_png({"metrics": [{"label": "a", "value": 1}], "trend": {"labels": ["猫", "b"], "values": [1, 2]}}, kind="card")
    with pytest.raises(ChartError, match=re.escape("trend.label")):
        render_png({"metrics": [{"label": "a", "value": 1}], "trend": {"label": "猫", "labels": ["a", "b"], "values": [1, 2]}}, kind="card")


def test_bad_theme():
    with pytest.raises(ChartError, match="theme должен быть"):
        render_png(SAMPLES["bar"], theme="blue")


def test_invalid_data_raises_before_drawing():
    with pytest.raises(ChartError):
        render_png({"labels": ["a"], "values": ["x"]})


def test_does_not_touch_pyplot_or_global_style():
    before = plt.rcParams.copy()
    plt.rcParams["font.family"] = "monospace"
    try:
        render_png(SAMPLES["bar"])
        assert plt.get_fignums() == []  # нет незакрытых фигур pyplot
    finally:
        plt.rcParams.update(before)


def test_no_memory_growth_on_many_renders():
    for _ in range(20):  # прогрев кешей шрифтов и matplotlib
        render_png(SAMPLES["line"])
    gc.collect()
    tracemalloc.start()
    start, _ = tracemalloc.get_traced_memory()
    for _ in range(150):
        render_png(SAMPLES["line"])
    gc.collect()
    end, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert end - start < 2 * 1024 * 1024


def test_parallel_threads_give_same_picture():
    # В async-ботах рисование уходит в потоки (asyncio.to_thread) — результат не должен зависеть от соседей.
    expected = render_png(SAMPLES["bar"]).getvalue()
    results, errors = [], []

    def work():
        try:
            for _ in range(5):
                results.append(render_png(SAMPLES["bar"]).getvalue())
        except Exception as e:  # noqa: BLE001 — ошибку потока передаём в тест
            errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert all(r == expected for r in results)
