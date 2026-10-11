from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthRead(BaseModel):
    status: Literal["ok"]


@router.get("/health")
async def health() -> HealthRead:
    return HealthRead(status="ok")
