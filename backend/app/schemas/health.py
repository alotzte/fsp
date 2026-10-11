from typing import Literal

from pydantic import BaseModel

DependencyStatus = Literal["ok", "unavailable"]


class HealthRead(BaseModel):
    status: Literal["ok", "degraded"]
    database: DependencyStatus
    scoring: DependencyStatus
