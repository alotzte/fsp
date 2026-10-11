from fastapi import APIRouter

from app.api import (
    assessment,
    ats,
    auth,
    candidate,
    cases,
    companies,
    consents,
    demo,
    dictionaries,
    employer,
    fsp,
    health,
    invitations,
    me,
)

api_router = APIRouter()
api_router.include_router(health.router)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth.router)
v1_router.include_router(me.router)
v1_router.include_router(candidate.router)
v1_router.include_router(assessment.router)
v1_router.include_router(cases.router)
v1_router.include_router(fsp.router)
v1_router.include_router(demo.router)
v1_router.include_router(employer.router)
v1_router.include_router(invitations.candidate_router)
v1_router.include_router(invitations.chat_router)
v1_router.include_router(invitations.inbox_router)
v1_router.include_router(invitations.vacancy_router)
v1_router.include_router(consents.router)
v1_router.include_router(companies.router)
v1_router.include_router(ats.tokens_router)
v1_router.include_router(ats.ats_router)
v1_router.include_router(dictionaries.router)
api_router.include_router(v1_router)
