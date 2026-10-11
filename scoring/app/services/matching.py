"""Ранжирование кандидатов под потребность работодателя и объяснение выдачи.

Скор: взвешенная сумма понятных вкладов (навыки, грейд, сила подтверждённого профиля,
ФСП, формат работы). Объяснения строятся из тех же вкладов детерминированно, поэтому
текст «почему кандидат здесь» никогда не расходится с позицией в выдаче.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.services.assessment.irt import CONFIDENCE_K, GRADE_THRESHOLDS

# Веса под потребность. ponytail: экспертные; подбирать по P@k на валидации
# (scoring/validation/matching.py), а после запуска: по принятым приглашениям.
NEED_WEIGHTS = {
    "skills": 0.40,
    "grade": 0.30,
    "strength": 0.10,
    "fsp": 0.10,
    "format": 0.10,
}
PROFILE_WEIGHTS = {"strength": 0.75, "fsp": 0.25}
# Нижняя граница «силы» для стажёра: у него нет порога в IRT.
_INTERN_FLOOR = -2.0
# Насколько резко растёт сила с запасом θ над порогом грейда (в единицах θ).
_STRENGTH_SCALE = 0.5
_NEIGHBOUR_GRADE_FIT = 0.4
# Априорная модель самооценки: заявленный грейд верен в 60% случаев, на ступень завышен
# в 30%. ponytail: экспертная оценка; после запуска: оценить по доле неподтверждённых
# заявок. Валидация проверяет устойчивость к другим долям (0-50%).
CLAIM_PRIOR = {0: 0.6, -1: 0.3, 1: 0.05, -2: 0.05}
# Диапазоны θ по грейдам; у крайних грейдов внешние границы условные (как в валидации).
LEVEL_BANDS = {
    0: (-2.5, GRADE_THRESHOLDS[1]),
    1: (GRADE_THRESHOLDS[1], GRADE_THRESHOLDS[2]),
    2: (GRADE_THRESHOLDS[2], GRADE_THRESHOLDS[3]),
    3: (GRADE_THRESHOLDS[3], GRADE_THRESHOLDS[4]),
    4: (GRADE_THRESHOLDS[4], 2.8),
}
_STRONG_RESULT = 0.8
_MAX_MISSING_IN_REASON = 3

CONTRIBUTION_TITLES = {
    "skills": "Навыки",
    "grade": "Грейд",
    "strength": "Результат теста",
    "fsp": "Достижения ФСП",
    "format": "Формат и город",
}


@dataclass(frozen=True)
class NeedSkill:
    id: int
    title: str
    must_have: bool


@dataclass(frozen=True)
class Need:
    grade_level: int | None
    skills: Sequence[NeedSkill] = ()
    work_formats: frozenset[str] = frozenset()
    city: str = ""
    salary_to: int | None = None


@dataclass(frozen=True)
class CandidateFeatures:
    key: int
    grade_level: int | None
    grade_title: str | None
    confirmed: bool
    theta: float | None = None
    theta_se: float | None = None
    skills: frozenset[int] = frozenset()
    work_formats: frozenset[str] = frozenset()
    city: str = ""
    # Нормированный бонус за результаты ФСП (0..1); 0: истории нет, без штрафа.
    fsp_score: float = 0.0
    # Победы, призовые места и финалы в реестре ФСП: для объяснения.
    fsp_achievements: int = 0
    # Из них: в дисциплине, профильной для направления кандидата: только для объяснения.
    fsp_relevant: int = 0
    salary_expectation: int | None = None
    # Заявленные навыки, которые подтвердил тест на грейд (подмножество skills).
    verified_skills: frozenset[int] = frozenset()
    # Верно решённых кейсов недели за последние 30 дней: свежий сигнал, только в объяснении,
    # на скор не влияет (вес менять: только по валидации).
    recent_cases: int = 0


SkillStatus = Literal["verified", "claimed", "missing"]


@dataclass(frozen=True)
class SkillCheck:
    """Навык потребности глазами работодателя: подтверждён тестом, только заявлен или нет."""

    title: str
    must_have: bool
    status: SkillStatus


@dataclass(frozen=True)
class Contribution:
    key: str
    title: str
    value: float
    weight: float


@dataclass(frozen=True)
class Match:
    key: int
    score: float
    salary_compatible: bool
    # Кандидат не рассматривает ни один из форматов работы потребности.
    format_compatible: bool
    contributions: list[Contribution]
    reasons: list[str] = field(default_factory=list)
    skills: list[SkillCheck] = field(default_factory=list)


def profile_strength(c: CandidateFeatures) -> float:
    """Сила подтверждённого профиля, 0..1. Неподтверждённый грейд: 0, подтверждённый: ≥ 0.5:
    запас консервативной оценки θ над порогом грейда через логистическую функцию."""
    if (
        not c.confirmed
        or c.theta is None
        or c.theta_se is None
        or c.grade_level is None
    ):
        return 0.0
    floor = GRADE_THRESHOLDS.get(c.grade_level, _INTERN_FLOOR)
    margin = c.theta - CONFIDENCE_K * c.theta_se - floor
    return 1.0 / (1.0 + math.exp(-margin / _STRENGTH_SCALE))


def _skills(need: Need, c: CandidateFeatures) -> tuple[float, list[NeedSkill]]:
    if not need.skills:
        return 1.0, []
    total = sum(2 if s.must_have else 1 for s in need.skills)
    hit = sum(2 if s.must_have else 1 for s in need.skills if s.id in c.skills)
    missing_must = [s for s in need.skills if s.must_have and s.id not in c.skills]
    return hit / total, missing_must


def skill_checks(need: Need, c: CandidateFeatures) -> list[SkillCheck]:
    def status(skill_id: int) -> SkillStatus:
        if skill_id in c.verified_skills:
            return "verified"
        return "claimed" if skill_id in c.skills else "missing"

    return [SkillCheck(s.title, s.must_have, status(s.id)) for s in need.skills]


def _band_likelihood(theta: float, se: float, level: int) -> float:
    """Правдоподобие оценки θ̂ ± SE, если истинный уровень где-то в диапазоне грейда:
    средняя плотность N(θ̂; θ, SE) по диапазону."""
    low, high = LEVEL_BANDS[level]

    def cdf(x: float) -> float:
        return 0.5 * (1 + math.erf((x - theta) / (se * math.sqrt(2))))

    return (cdf(high) - cdf(low)) / (high - low)


def level_posterior(c: CandidateFeatures) -> dict[int, float]:
    """Распределение истинного грейда кандидата.

    Априорно: заявленный грейд с поправкой на завышение самооценки (CLAIM_PRIOR); результат
    любой попытки теста (θ̂ ± SE), пройденной или нет, уточняет его по правилу Байеса.
    """
    if c.grade_level is None:
        return {}
    prior = {
        c.grade_level + shift: p
        for shift, p in CLAIM_PRIOR.items()
        if c.grade_level + shift in LEVEL_BANDS
    }
    if c.theta is not None and c.theta_se is not None:
        theta, se = c.theta, c.theta_se
        prior = {lvl: p * _band_likelihood(theta, se, lvl) for lvl, p in prior.items()}
    total = sum(prior.values())
    return {lvl: p / total for lvl, p in prior.items()} if total > 0 else {}


def _grade(need: Need, c: CandidateFeatures) -> float:
    """Ожидаемое соответствие грейду: вероятность, что истинный уровень кандидата
    равен запрошенному (соседний грейд засчитывается частично)."""
    if need.grade_level is None:
        return 1.0
    fit = {0: 1.0, 1: _NEIGHBOUR_GRADE_FIT}
    return sum(
        p * fit.get(abs(lvl - need.grade_level), 0.0)
        for lvl, p in level_posterior(c).items()
    )


# Как города пишут в профилях: «СПб», «г. Москва». Сравниваем по ключу, а не по строке.
_CITY_ALIASES = {"спб": "санкт-петербург", "питер": "санкт-петербург", "мск": "москва"}


def city_key(city: str) -> str:
    key = city.strip().casefold().replace("ё", "е")
    key = key.removeprefix("город ").removeprefix("г.").removesuffix(" г.").strip()
    return _CITY_ALIASES.get(key, key)


def _format(need: Need, c: CandidateFeatures) -> float:
    # Незаполненный формат или город кандидата: неизвестность, а не несовпадение: не штрафуем.
    parts = []
    if need.work_formats and c.work_formats:
        parts.append(1.0 if need.work_formats & c.work_formats else 0.0)
    if need.city and c.city.strip():
        remote_ok = "remote" in need.work_formats and "remote" in c.work_formats
        parts.append(
            1.0 if city_key(c.city) == city_key(need.city) or remote_ok else 0.0
        )
    return sum(parts) / len(parts) if parts else 1.0


def _reasons(
    need: Need | None,
    c: CandidateFeatures,
    values: dict[str, float],
    missing: list[NeedSkill],
) -> list[str]:
    reasons = []
    if need is not None and need.skills:
        must = [s for s in need.skills if s.must_have]
        nice_hit = sum(1 for s in need.skills if not s.must_have and s.id in c.skills)
        if must and not missing:
            reasons.append("Есть все обязательные навыки")
        elif must:
            names = ", ".join(s.title for s in missing[:_MAX_MISSING_IN_REASON])
            more = "..." if len(missing) > _MAX_MISSING_IN_REASON else ""
            reasons.append(
                f"Обязательные навыки: {len(must) - len(missing)} из {len(must)} "
                f"(нет {names}{more})"
            )
        if nice_hit:
            reasons.append(f"Желательных навыков: {nice_hit}")
        verified = [s.title for s in need.skills if s.id in c.verified_skills]
        if verified:
            reasons.append(
                f"Подтверждено тестом {len(verified)} из {len(need.skills)} навыков "
                f"потребности: {', '.join(verified)}"
            )
    if c.confirmed and c.grade_title:
        strong = values["strength"] >= _STRONG_RESULT
        reasons.append(
            f"Грейд {c.grade_title} подтверждён тестом"
            + (", уверенный запас над порогом" if strong else "")
        )
    else:
        reasons.append("Грейд не подтверждён тестом")
    if need is not None and need.grade_level is not None:
        if c.grade_level is not None and c.grade_level != need.grade_level:
            reasons.append("Грейд в категории отличается от запрошенного")
        if c.theta is not None:
            chance = level_posterior(c).get(need.grade_level, 0.0)
            reasons.append(
                f"По тесту уровень соответствует запрошенному с вероятностью {chance:.0%}"
            )
    if c.recent_cases:
        reasons.append(f"Решает кейсы недели: {c.recent_cases} за 30 дней")
    if values["fsp"] > 0:
        if not c.fsp_achievements:
            reasons.append("Есть результаты в соревнованиях ФСП")
        else:
            relevant = (
                f", из них по профильной дисциплине: {c.fsp_relevant}"
                if c.fsp_relevant
                else ""
            )
            reasons.append(
                f"Достижения ФСП: {c.fsp_achievements} (победы, призовые места, финалы){relevant}"
            )
    if need is not None:
        if (
            need.work_formats
            and c.work_formats
            and not need.work_formats & c.work_formats
        ):
            reasons.append("Кандидат не рассматривает формат работы из потребности")
        elif need.city and _format(need, c) < 1.0:
            reasons.append("Кандидат в другом городе")
    return reasons


def match_candidate(need: Need | None, c: CandidateFeatures) -> Match:
    values = {"strength": profile_strength(c), "fsp": max(0.0, min(1.0, c.fsp_score))}
    missing: list[NeedSkill] = []
    checks: list[SkillCheck] = []
    salary_ok = format_ok = True
    if need is None:
        weights = PROFILE_WEIGHTS
    else:
        weights = NEED_WEIGHTS
        # ТЗ: сила подтверждённого профиля ранжирует кандидатов внутри категории; кандидату
        # соседнего грейда большой запас над порогом своего грейда преимущества не даёт.
        if need.grade_level is not None and c.grade_level != need.grade_level:
            values["strength"] = 0.0
        values["skills"], missing = _skills(need, c)
        checks = skill_checks(need, c)
        values["grade"] = _grade(need, c)
        values["format"] = _format(need, c)
        salary_ok = (
            need.salary_to is None
            or c.salary_expectation is None
            or need.salary_to >= c.salary_expectation
        )
        format_ok = (
            not need.work_formats
            or not c.work_formats
            or bool(need.work_formats & c.work_formats)
        )
    reasons = _reasons(need, c, values, missing)
    if not salary_ok:
        reasons.append("Верх вилки ниже ожиданий кандидата: приглашение не отправить")
    return Match(
        key=c.key,
        score=sum(weights[k] * values[k] for k in weights),
        salary_compatible=salary_ok,
        format_compatible=format_ok,
        contributions=[
            Contribution(k, CONTRIBUTION_TITLES[k], values[k], w)
            for k, w in weights.items()
        ],
        reasons=reasons,
        skills=checks,
    )


def rank(need: Need | None, candidates: Sequence[CandidateFeatures]) -> list[Match]:
    """Сначала совместимые по вилке, затем по формату работы (это условия кандидата, а не
    пожелания); внутри по скору, при равенстве по ключу, чтобы порядок был стабильным."""
    matches = [match_candidate(need, c) for c in candidates]
    return sorted(
        matches,
        key=lambda m: (
            not m.salary_compatible,
            not m.format_compatible,
            -m.score,
            m.key,
        ),
    )
