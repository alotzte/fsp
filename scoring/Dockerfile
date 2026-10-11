FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

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

EXPOSE 8001
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
