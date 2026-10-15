"""Утилита командной строки."""

import json
import subprocess
import sys

import pytest

from botgraf.cli import main

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DATA = {"labels": ["Кошки", "Собаки"], "values": [12, 8]}


@pytest.fixture
def data_file(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps(DATA, ensure_ascii=False), encoding="utf-8")
    return path


def test_png_to_file(data_file, tmp_path):
    out = tmp_path / "chart.png"
    assert main([str(data_file), "-k", "pie", "-t", "dark", "-o", str(out)]) == 0
    assert out.read_bytes().startswith(PNG_SIGNATURE)


def test_text_to_stdout(data_file, capsys):
    assert main([str(data_file), "--text"]) == 0
    assert capsys.readouterr().out == "Кошки   ██████████  12\nСобаки  ██████▋      8\n"


def test_bad_data_exit_2(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text('{"labels": ["a"], "values": ["x"]}')
    assert main([str(path), "--text"]) == 2
    assert capsys.readouterr().err == "ошибка: values[0] должно быть числом, получено 'x'\n"


def test_missing_file_exit_1(tmp_path, capsys):
    assert main([str(tmp_path / "nope.json"), "-o", str(tmp_path / "x.png")]) == 1
    assert "nope.json" in capsys.readouterr().err


def test_output_required(data_file, capsys):
    with pytest.raises(SystemExit) as e:
        main([str(data_file)])
    assert e.value.code == 2  # argparse: нужен -o или --text


def test_module_run_from_stdin_to_stdout():
    # python -m botgraf - -o - : данные из stdin, PNG в stdout — для конвейеров.
    result = subprocess.run(
        [sys.executable, "-m", "botgraf", "-", "-k", "line", "-o", "-"],
        input=json.dumps(DATA).encode(), capture_output=True, check=True,
    )
    assert result.stdout.startswith(PNG_SIGNATURE)
