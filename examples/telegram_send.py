"""Отправка графика в Telegram без фреймворков — только стандартная библиотека.

    BOT_TOKEN=123:abc CHAT_ID=42 python3 examples/telegram_send.py

В aiogram / python-telegram-bot то же самое — передать render_png(...) в метод отправки фото.
"""

import json
import os
import urllib.request
import uuid

from botgraf import ChartError, render_png, render_text

API = os.environ.get("TELEGRAM_API", "https://api.telegram.org")


def send_photo(token: str, chat_id: str, png: bytes, caption: str) -> dict:
    boundary = uuid.uuid4().hex
    parts = [
        _field(boundary, "chat_id", chat_id),
        _field(boundary, "caption", caption),
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="botgraf.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode() + png + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    request = urllib.request.Request(
        f"{API}/bot{token}/sendPhoto",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _field(boundary: str, name: str, value: str) -> bytes:
    return f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()


def main() -> None:
    stats = {"title": "Найдено на фото за день", "labels": ["Кошки", "Собаки"], "values": [12, 8]}
    try:
        png = render_png(stats, kind="bar", theme="light")
    except ChartError as e:
        print(f"Отчёт не построен: {e}")
        return
    result = send_photo(os.environ["BOT_TOKEN"], os.environ["CHAT_ID"], png.getvalue(), caption=stats["title"])
    print("Отправлено" if result.get("ok") else result)
    # Если фото отправлять нельзя — тот же отчёт текстом (моноширинным, чтобы столбики выровнялись):
    print(render_text(stats, kind="bar"))


if __name__ == "__main__":
    main()
