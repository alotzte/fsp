FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Шрифты с кириллицей для PDF-профиля (app/api/profile_pdf.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PATH="/srv/.venv/bin:$PATH"

# Зависимости отдельным слоем: пересобираются только при изменении lock-файла.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
