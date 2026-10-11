from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.health import DependencyStatus, HealthRead
from app.services.db.session import SessionDep
from app.services.scoring import ScoringClientDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: SessionDep, scoring: ScoringClientDep) -> HealthRead:
    database: DependencyStatus = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        database = "unavailable"

    scoring_status: DependencyStatus = "ok" if await scoring.is_healthy() else "unavailable"
    is_ok = database == "ok" and scoring_status == "ok"
    return HealthRead(
        status="ok" if is_ok else "degraded", database=database, scoring=scoring_status
    )
