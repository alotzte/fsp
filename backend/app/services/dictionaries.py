import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from app.errors import DomainError
from app.services.db.models import Grade, Industry, Skill, SkillKind, Specialization
from app.services.db.session import SessionDep

_WHITESPACE = re.compile(r"\s+")


class UnknownSkillError(DomainError):
    message = "Навык не найден в справочнике"


class UnknownSpecializationError(DomainError):
    message = "Специализация не найдена в справочнике"


class UnknownIndustryError(DomainError):
    message = "Отрасль не найдена в справочнике"


@dataclass(frozen=True)
class SkillRequest:
    """Навык от пользователя: id из справочника или произвольное название."""

    skill_id: int | None
    title: str | None


@dataclass(frozen=True)
class ResolvedSkill:
    skill: Skill | None
    custom_title: str | None


def normalize_skill_title(title: str) -> str:
    return _WHITESPACE.sub(" ", title).strip()


class DictionaryService:
    """Справочники: специализации, грейды, навыки, отрасли."""

    def __init__(self, session: SessionDep) -> None:
        self._session = session

    async def list_specializations(self) -> Sequence[Specialization]:
        result = await self._session.scalars(select(Specialization).order_by(Specialization.title))
        return result.all()

    async def list_grades(self) -> Sequence[Grade]:
        result = await self._session.scalars(select(Grade).order_by(Grade.level))
        return result.all()

    async def list_skills(self, kind: SkillKind) -> Sequence[Skill]:
        result = await self._session.scalars(
            select(Skill).where(Skill.kind == kind).order_by(Skill.title)
        )
        return result.all()

    async def list_industries(self) -> Sequence[Industry]:
        result = await self._session.scalars(select(Industry).order_by(Industry.title))
        return result.all()

    async def require_specialization(self, specialization_id: int) -> Specialization:
        specialization = await self._session.get(Specialization, specialization_id)
        if specialization is None:
            raise UnknownSpecializationError
        return specialization

    async def require_industry(self, industry_id: int) -> Industry:
        industry = await self._session.get(Industry, industry_id)
        if industry is None:
            raise UnknownIndustryError
        return industry

    async def resolve_skills(
        self, requests: Sequence[SkillRequest], kind: SkillKind
    ) -> list[ResolvedSkill]:
        """Приводит навыки пользователя к справочнику и убирает дубли.

        Свой тег, совпавший с названием или синонимом из справочника (без учёта регистра),
        становится ссылкой на справочник: «react.js» → React. Иначе остаётся своим тегом.
        """
        dictionary = await self.list_skills(kind)
        by_id = {skill.id: skill for skill in dictionary}
        by_name: dict[str, Skill] = {}
        for skill in dictionary:
            for name in (skill.title, *skill.aliases):
                by_name.setdefault(name.casefold(), skill)

        resolved: list[ResolvedSkill] = []
        seen: set[str] = set()
        for request in requests:
            if request.skill_id is not None:
                known = by_id.get(request.skill_id)
                if known is None:
                    raise UnknownSkillError
                item = ResolvedSkill(skill=known, custom_title=None)
            else:
                title = normalize_skill_title(request.title or "")
                matched = by_name.get(title.casefold())
                item = ResolvedSkill(
                    skill=matched, custom_title=None if matched is not None else title
                )
            dedupe_key = (
                f"id:{item.skill.id}" if item.skill else f"tag:{item.custom_title!s}".casefold()
            )
            if dedupe_key not in seen:
                seen.add(dedupe_key)
                resolved.append(item)
        return resolved


DictionaryServiceDep = Annotated[DictionaryService, Depends()]
