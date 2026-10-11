from fastapi import APIRouter

from app.schemas.matching import (
    ContributionRead,
    MatchRead,
    RankRequest,
    SkillCheckRead,
)
from app.services.matching import CandidateFeatures, Need, NeedSkill, rank

router = APIRouter(prefix="/matching", tags=["matching"])


@router.post("/rank")
async def rank_candidates(payload: RankRequest) -> list[MatchRead]:
    """Ранжирует переданных кандидатов и объясняет позицию каждого."""
    need = (
        Need(
            grade_level=payload.need.grade_level,
            skills=[NeedSkill(s.id, s.title, s.must_have) for s in payload.need.skills],
            work_formats=frozenset(payload.need.work_formats),
            city=payload.need.city,
            salary_to=payload.need.salary_to,
        )
        if payload.need
        else None
    )
    candidates = [
        CandidateFeatures(
            key=c.key,
            grade_level=c.grade_level,
            grade_title=c.grade_title,
            confirmed=c.confirmed,
            theta=c.theta,
            theta_se=c.theta_se,
            skills=frozenset(c.skills),
            work_formats=frozenset(c.work_formats),
            city=c.city,
            fsp_score=c.fsp_score,
            fsp_achievements=c.fsp_achievements,
            fsp_relevant=c.fsp_relevant,
            salary_expectation=c.salary_expectation,
            verified_skills=frozenset(c.verified_skills),
            recent_cases=c.recent_cases,
        )
        for c in payload.candidates
    ]
    return [
        MatchRead(
            key=m.key,
            score=m.score,
            salary_compatible=m.salary_compatible,
            format_compatible=m.format_compatible,
            contributions=[
                ContributionRead(
                    key=x.key, title=x.title, value=x.value, weight=x.weight
                )
                for x in m.contributions
            ],
            reasons=m.reasons,
            skills=[
                SkillCheckRead(title=x.title, must_have=x.must_have, status=x.status)
                for x in m.skills
            ],
        )
        for m in rank(need, candidates)
    ]
