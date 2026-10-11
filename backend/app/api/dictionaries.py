from collections.abc import Sequence

from fastapi import APIRouter

from app.schemas.dictionaries import (
    GradeRead,
    IndustryRead,
    SkillDictionaryRead,
    SpecializationRead,
)
from app.services.db.models import Grade, Industry, Skill, SkillKind, Specialization
from app.services.dictionaries import DictionaryServiceDep

router = APIRouter(prefix="/dictionaries", tags=["dictionaries"])


@router.get("/specializations", response_model=list[SpecializationRead])
async def list_specializations(
    service: DictionaryServiceDep,
) -> Sequence[Specialization]:
    return await service.list_specializations()


@router.get("/grades", response_model=list[GradeRead])
async def list_grades(service: DictionaryServiceDep) -> Sequence[Grade]:
    return await service.list_grades()


@router.get("/skills", response_model=list[SkillDictionaryRead])
async def list_skills(kind: SkillKind, service: DictionaryServiceDep) -> Sequence[Skill]:
    """Весь справочник навыков одного вида: он небольшой, фронт фильтрует его сам при вводе."""
    return await service.list_skills(kind)


@router.get("/industries", response_model=list[IndustryRead])
async def list_industries(service: DictionaryServiceDep) -> Sequence[Industry]:
    return await service.list_industries()
