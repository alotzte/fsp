from collections.abc import Sequence
from typing import Annotated, Literal

import httpx
from fastapi import Depends, Request, status
from pydantic import BaseModel, TypeAdapter

from app.errors import DomainError
from app.services.db.models import ItemKind


class ScoringUnavailableError(DomainError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "Сервис оценки недоступен, попробуйте позже"


# Контракт сервиса scoring (scoring/app/schemas/assessment.py).
class CompetencyQuota(BaseModel):
    slug: str
    title: str
    count: int


class Blueprint(BaseModel):
    specialization: str
    items_count: int
    time_limit_minutes: int
    competencies: list[CompetencyQuota]


class AssembledItem(BaseModel):
    family_id: str
    competency: str
    competency_title: str
    a: float
    b: float
    kind: ItemKind
    prompt: str
    code: str | None
    options: list[str]
    answer: str


class ScoreItem(BaseModel):
    a: float
    b: float
    answer: str
    response: str | None
    # Эталоны чужих экземпляров того же семейства: для детектора утечки.
    foreign_answers: list[str] = []


class ScoreResult(BaseModel):
    theta: float
    se: float
    passed: bool
    strong: bool
    estimated_level: int
    # Сколько заданий у порога добавить перед решением; 0 значит, что решение окончательное.
    extend_items: int
    retest_agreement: float
    correct: list[bool]
    foreign_matches: list[bool]


class NeedSkillFeature(BaseModel):
    id: int
    title: str
    must_have: bool


class NeedFeatures(BaseModel):
    grade_level: int | None
    skills: list[NeedSkillFeature]
    work_formats: list[str]
    city: str
    salary_to: int | None


class CandidateFeatures(BaseModel):
    key: int
    grade_level: int | None
    grade_title: str | None
    confirmed: bool
    theta: float | None
    theta_se: float | None
    skills: list[int]
    work_formats: list[str]
    city: str
    fsp_score: float = 0.0
    fsp_achievements: int = 0
    # Из них: в профильной для направления дисциплине; только для объяснения.
    fsp_relevant: int = 0
    salary_expectation: int | None
    verified_skills: list[int] = []
    # Верно решённых кейсов недели за 30 дней: только для объяснения, на скор не влияет.
    recent_cases: int = 0


class Contribution(BaseModel):
    key: str
    title: str
    value: float
    weight: float


class SkillCheck(BaseModel):
    title: str
    must_have: bool
    status: Literal["verified", "claimed", "missing"]


class MatchResult(BaseModel):
    key: int
    score: float
    salary_compatible: bool
    format_compatible: bool
    contributions: list[Contribution]
    reasons: list[str]
    skills: list[SkillCheck] = []


_BLUEPRINTS = TypeAdapter(list[Blueprint])
_MATCHES = TypeAdapter(list[MatchResult])
_ITEMS = TypeAdapter(list[AssembledItem])


class ScoringClient:
    """HTTP-клиент к сервису scoring. Scoring без состояния: все данные идут в запросе."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def is_healthy(self) -> bool:
        try:
            response = await self._http.get("/health")
        except httpx.HTTPError:
            return False
        return response.is_success

    async def list_blueprints(self) -> list[Blueprint]:
        return _BLUEPRINTS.validate_python(await self._request("GET", "/assessment/blueprints"))

    async def assemble(
        self,
        *,
        specialization: str,
        level: int,
        seed: int,
        recent_families: Sequence[str],
        length: int | None = None,
    ) -> list[AssembledItem]:
        """length: экспресс-тест из стольких заданий (пропорции компетенций сохраняются)."""
        payload = {
            "specialization": specialization,
            "level": level,
            "seed": seed,
            "recent_families": list(recent_families),
            "length": length,
        }
        return _ITEMS.validate_python(await self._request("POST", "/assessment/assemble", payload))

    async def case(self, *, specialization: str, level: int, seed: int) -> AssembledItem:
        """Кейс недели: одно задание направления у сложности уровня."""
        payload = {"specialization": specialization, "level": level, "seed": seed}
        return AssembledItem.model_validate(
            await self._request("POST", "/assessment/case", payload)
        )

    async def extend(
        self,
        *,
        specialization: str,
        level: int,
        seed: int,
        count: int,
        attempt_families: Sequence[str],
        recent_families: Sequence[str],
    ) -> list[AssembledItem]:
        """Задания продления попытки: семейства у порога грейда, ещё не показанные в ней."""
        payload = {
            "specialization": specialization,
            "level": level,
            "seed": seed,
            "count": count,
            "attempt_families": list(attempt_families),
            "recent_families": list(recent_families),
        }
        return _ITEMS.validate_python(await self._request("POST", "/assessment/extend", payload))

    async def score(
        self, *, level: int, items: Sequence[ScoreItem], extensions: int, express: bool
    ) -> ScoreResult:
        """extensions: сколько раз попытку уже продлевали: scoring решает, продлевать ли ещё."""
        payload = {
            "level": level,
            "items": [item.model_dump() for item in items],
            "extensions": extensions,
            "express": express,
        }
        return ScoreResult.model_validate(
            await self._request("POST", "/assessment/score", payload)
        )

    async def rank(
        self, need: NeedFeatures | None, candidates: Sequence[CandidateFeatures]
    ) -> list[MatchResult]:
        """Кандидаты в порядке выдачи с вкладами и объяснениями."""
        payload = {
            "need": need.model_dump() if need else None,
            "candidates": [c.model_dump() for c in candidates],
        }
        return _MATCHES.validate_python(await self._request("POST", "/matching/rank", payload))

    async def _request(self, method: str, url: str, payload: object = None) -> object:
        try:
            response = await self._http.request(method, url, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # Сюда же попадает 404 «нет теста для направления»: backend сверяется со списком
            # blueprints до сборки, поэтому 404: рассинхрон сервисов, а не ошибка ввода.
            raise ScoringUnavailableError from exc
        return response.json()


def get_scoring_client(request: Request) -> ScoringClient:
    # Один AsyncClient на всё приложение (создаётся в lifespan), чтобы переиспользовать соединения.
    return ScoringClient(request.app.state.scoring_http)


ScoringClientDep = Annotated[ScoringClient, Depends(get_scoring_client)]
