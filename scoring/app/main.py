from fastapi import FastAPI

from app.api.router import api_router


def create_app() -> FastAPI:
    # Сервис без состояния: в БД не ходит, все данные для расчёта приходят в запросе от backend.
    app = FastAPI(title="FSP Scoring")
    app.include_router(api_router)
    return app
