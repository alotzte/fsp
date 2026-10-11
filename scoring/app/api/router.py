from fastapi import APIRouter

from app.api import assessment, health, matching

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(assessment.router)
api_router.include_router(matching.router)
