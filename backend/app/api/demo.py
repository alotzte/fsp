from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.config import SettingsDep
from app.errors import error_responses
from app.services.auth.dependencies import SESSION_COOKIE
from app.services.db.models import UserRole
from app.services.demo import DemoModeDisabledError, DemoServiceDep

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoConfigRead(BaseModel):
    enabled: bool


class DemoLoginInput(BaseModel):
    role: UserRole


class DemoLoginRead(BaseModel):
    role: UserRole


@router.get("")
async def get_demo_config(demo: DemoServiceDep) -> DemoConfigRead:
    """Включён ли демо-режим для жюри."""
    return DemoConfigRead(enabled=demo.enabled)


@router.post("/login", responses=error_responses(DemoModeDisabledError))
async def demo_login(
    payload: DemoLoginInput, response: Response, demo: DemoServiceDep, settings: SettingsDep
) -> DemoLoginRead:
    """Вход в новую песочницу кандидата или работодателя без регистрации (только DEMO_MODE)."""
    token = await demo.login(payload.role)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(demo.session_lifetime.total_seconds()),
        path=f"{settings.public_path}/",
        httponly=True,
        secure=settings.uses_https,
        samesite="lax",
    )
    return DemoLoginRead(role=payload.role)
