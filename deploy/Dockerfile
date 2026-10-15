FROM python:3.12-slim

WORKDIR /app
# Шрифт DejaVu Sans идёт внутри matplotlib — системные шрифты в образе не нужны.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[aiogram]'
COPY examples ./examples

# Файловая система контейнера только для чтения: кэш шрифтов matplotlib — во временной папке.
ENV MPLCONFIGDIR=/tmp/matplotlib PYTHONUNBUFFERED=1
USER 65534
CMD ["python", "examples/web.py"]
