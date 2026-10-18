"""Утилита командной строки: botgraph data.json -o chart.png

Коды выхода: 0 — готово, 1 — не прочитать или не записать файл, 2 — ошибка в данных или аргументах.
"""

import argparse
import sys
from pathlib import Path

from .png import render_png
from .schema import KINDS, BotGraphValidationError
from .text import render_text
from .themes import THEMES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="botgraph", description="График для чат-бота из JSON: PNG-картинка или текст.")
    parser.add_argument("file", help="JSON-файл с данными; - — читать из stdin")
    parser.add_argument("-k", "--kind", default="bar", choices=KINDS, help="вид графика (по умолчанию bar)")
    parser.add_argument("-t", "--theme", default="light", choices=tuple(THEMES), help="тема (по умолчанию light)")
    out = parser.add_mutually_exclusive_group(required=True)
    out.add_argument("-o", "--output", help="куда записать PNG; - — в stdout")
    out.add_argument("--text", action="store_true", help="напечатать текстовый вариант вместо картинки")
    args = parser.parse_args(argv)

    try:
        raw = sys.stdin.buffer.read() if args.file == "-" else Path(args.file).read_bytes()
        if args.text:
            print(render_text(raw, args.kind))
            return 0
        png = render_png(raw, args.kind, args.theme).getvalue()
        if args.output == "-":
            sys.stdout.buffer.write(png)
        else:
            Path(args.output).write_bytes(png)
    except BotGraphValidationError as e:
        print(f"ошибка: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ошибка: {e.filename}: {e.strerror}", file=sys.stderr)
        return 1
    return 0
