FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ffmpeg нужен для нормализации результата: 720p, H.264, AAC, faststart.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app

# Индекс задаётся снаружи: по умолчанию PyPI, при необходимости — зеркало.
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" .

# --- приложение ---------------------------------------------------------
FROM base AS runtime

CMD ["python", "-m", "app.main_bot"]

# --- тесты --------------------------------------------------------------
FROM base AS test

ARG PIP_INDEX_URL=https://pypi.org/simple

COPY tests ./tests
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -e ".[dev]"

# HTML-отчёт складывается в ./reports через volume, чтобы не засорять систему.
CMD ["pytest", "-q", "--html=reports/report.html", "--self-contained-html"]
