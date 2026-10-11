from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.router import api_router
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.services.admin.setup import setup_admin
from app.services.auth.keycloak import KeycloakClient, OidcRealm
from app.services.db.session import build_engine, build_session_maker
from app.services.storage import LocalFileStorage


def _operation_id_from_handler_name(route: APIRoute) -> str:
    # operationId = имя функции ручки: фронт генерирует из него хуки (useListGrades и т.п.).
    # Поэтому имена функций ручек должны быть уникальны во всём API.
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # Движок создаётся сразу, а не в lifespan: SQLAdmin нужен engine при монтировании.
    engine = build_engine(str(settings.database_url))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.session_maker = build_session_maker(engine)
        async with AsyncExitStack() as stack:
            app.state.scoring_http = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=settings.scoring_url,
                    timeout=settings.scoring_timeout_seconds,
                )
            )
            keycloak_http = await stack.enter_async_context(
                httpx.AsyncClient(timeout=settings.keycloak_timeout_seconds)
            )
            app.state.keycloak = KeycloakClient(OidcRealm.login(settings), keycloak_http)
            app.state.fsp_id = KeycloakClient(OidcRealm.fsp_id(settings), keycloak_http)
            yield
        await engine.dispose()

    app = FastAPI(
        title="FSP Backend",
        # Префикс публикации: gateway передаёт его в пути, ссылки админки и /docs строятся с ним.
        root_path=settings.public_path,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id_from_handler_name,
    )
    app.state.settings = settings
    app.state.file_storage = LocalFileStorage(Path(settings.upload_dir))
    register_error_handlers(app)
    app.include_router(api_router)
    setup_admin(app, engine, settings)
    return app
