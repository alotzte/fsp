from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.services.admin.auth import AdminAuthBackend
from app.services.admin.views import ADMIN_VIEWS


def setup_admin(app: FastAPI, engine: AsyncEngine, settings: Settings) -> Admin:
    admin = Admin(
        app,
        engine,
        title="FSP Admin",
        authentication_backend=AdminAuthBackend(settings),
    )
    for view in ADMIN_VIEWS:
        admin.add_view(view)
    return admin
