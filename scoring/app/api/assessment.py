from fastapi import APIRouter, HTTPException, status

from app.schemas.assessment import (
    AssembledItemRead,
    AssembleRequest,
    BlueprintRead,
    CaseRequest,
    CompetencyQuotaRead,
    ExtendRequest,
    ScoreRead,
    ScoreRequest,
)
from app.services.assessment.assembly import (
    BLUEPRINTS,
    COMPETENCY_TITLES,
    AssembledItem,
    Blueprint,
    ScoredResponse,
    assemble,
    extend,
    extension_size,
    score_attempt,
    shortened,
    weekly_case,
)

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.get("/blueprints")
async def list_blueprints() -> list[BlueprintRead]:
    """Направления, для которых есть тест, и состав теста."""
    return [
        BlueprintRead(
            specialization=bp.specialization,
            items_count=bp.items_count,
            time_limit_minutes=bp.time_limit_minutes,
            competencies=[
                CompetencyQuotaRead(
                    slug=slug, title=COMPETENCY_TITLES[slug], count=count
                )
                for slug, count in bp.quotas.items()
            ],
        )
        for bp in BLUEPRINTS.values()
    ]


def _blueprint(specialization: str) -> Blueprint:
    blueprint = BLUEPRINTS.get(specialization)
    if blueprint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Для направления нет теста")
    return blueprint


def _item_read(it: AssembledItem) -> AssembledItemRead:
    return AssembledItemRead(
        family_id=it.family.id,
        competency=it.family.competency,
        competency_title=COMPETENCY_TITLES[it.family.competency],
        a=it.family.a,
        b=it.family.b,
        kind=it.item.kind,
        prompt=it.item.prompt,
        code=it.item.code,
        options=it.item.options,
        answer=it.item.answer,
    )


@router.post("/assemble")
async def assemble_test(payload: AssembleRequest) -> list[AssembledItemRead]:
    blueprint = _blueprint(payload.specialization)
    if payload.length is not None:
        blueprint = shortened(blueprint, payload.length)
    return [
        _item_read(it)
        for it in assemble(
            blueprint, payload.level, payload.seed, set(payload.recent_families)
        )
    ]


@router.post("/case")
async def weekly_case_item(payload: CaseRequest) -> AssembledItemRead:
    """«Кейс недели»: одно задание направления у сложности уровня кандидата."""
    return _item_read(
        weekly_case(_blueprint(payload.specialization), payload.level, payload.seed)
    )


@router.post("/extend")
async def extend_test(payload: ExtendRequest) -> list[AssembledItemRead]:
    """Задания продления попытки у порога грейда."""
    return [
        _item_read(it)
        for it in extend(
            _blueprint(payload.specialization),
            payload.level,
            payload.seed,
            payload.count,
            set(payload.attempt_families),
            set(payload.recent_families),
        )
    ]


@router.post("/score")
async def score_test(payload: ScoreRequest) -> ScoreRead:
    result = score_attempt(
        payload.level,
        [
            ScoredResponse(i.a, i.b, i.answer, i.response, i.foreign_answers)
            for i in payload.items
        ],
    )
    return ScoreRead(
        theta=result.estimate.theta,
        se=result.estimate.se,
        passed=result.decision.passed,
        strong=result.decision.strong,
        estimated_level=result.decision.estimated_level,
        extend_items=extension_size(
            near_threshold=result.decision.near_threshold,
            extensions=payload.extensions,
            express=payload.express,
        ),
        retest_agreement=result.decision.retest_agreement,
        correct=result.correct,
        foreign_matches=result.foreign_matches,
    )
