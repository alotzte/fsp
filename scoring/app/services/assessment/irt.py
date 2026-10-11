"""IRT-модель 2PL: оценка уровня кандидата θ по ответам и правило присвоения грейда.

Вероятность верного ответа на задание с дискриминативностью a и сложностью b:
    P(θ) = 1 / (1 + exp(−a·(θ − b)))
θ и задания живут на одной шкале, поэтому оценки сопоставимы между кандидатами, которым
достались разные задания: это и снимает противоречие «уникальные задания vs объективность».
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

# Пороги θ по уровню грейда (grades.level в backend): 0 стажёр, 1 junior, 2 middle,
# 3 senior, 4 lead. У стажёра порога нет, это стартовый уровень.
# ponytail: пороги экспертные, до калибровки на реальных ответах; пересчитать по пилоту
# (модифицированный метод Ангоффа → тестовая характеристическая кривая).
GRADE_THRESHOLDS: dict[int, float] = {1: -1.0, 2: 0.0, 3: 1.0, 4: 1.8}
MAX_LEVEL = 4

# Грейд подтверждается, если θ − K·SE ≥ порога: короткий тест даёт заметную погрешность,
# и запас против завышения важнее, чем против занижения (ошибочно не подтверждённый
# кандидат перепройдёт тест, а ошибочно подтверждённый портит выдачу работодателю).
# K = 0.25 подобран по scoring/validation/assessment.py: при 0.5 заметно больше честных
# кандидатов не подтверждаются, при 0 завышение на грейд выше доходит до 20-25%.
CONFIDENCE_K = 0.25

# Априорное N(0, PRIOR_SD²) для EAP. При стандартном N(0, 1) оценка сильно стягивалась к нулю
# у верхних грейдов: честного Lead тест подтверждал в 41% попыток, Senior: в 55%. 1.25 подобрано
# симуляцией: вместе с продлением у порога честный Senior и Lead ≈ 70%, а завышение Senior→Lead
# остаётся в пределах 10% (при 1.5: до 13%).
PRIOR_SD = 1.25
# Сетка для EAP: интегрирование суммой по равномерной сетке.
_GRID = [-4.0 + 0.05 * i for i in range(161)]
_PRIOR = [math.exp(-0.5 * (theta / PRIOR_SD) ** 2) for theta in _GRID]


@dataclass(frozen=True)
class ItemResponse:
    a: float
    b: float
    correct: bool


@dataclass(frozen=True)
class AbilityEstimate:
    theta: float
    se: float


@dataclass(frozen=True)
class GradeDecision:
    passed: bool
    # Уверенно выше следующего уровня: системе стоит предложить тест на грейд выше.
    strong: bool
    # Максимальный уровень, который подтверждает эта попытка (может быть ниже заявленного).
    estimated_level: int
    # Порог ближе одной SE к оценке: решение неуверенное, попытке нужны задания у порога.
    near_threshold: bool
    # Вероятность, что повторная попытка на этот грейд даст то же решение.
    retest_agreement: float


def probability(theta: float, a: float, b: float) -> float:
    return 1.0 / (1.0 + math.exp(-a * (theta - b)))


def estimate_ability(responses: Sequence[ItemResponse]) -> AbilityEstimate:
    """EAP-оценка θ и её стандартная ошибка (стандартное отклонение апостериорного)."""
    weights = []
    for theta, prior in zip(_GRID, _PRIOR, strict=True):
        likelihood = prior
        for response in responses:
            p = probability(theta, response.a, response.b)
            likelihood *= p if response.correct else 1.0 - p
        weights.append(likelihood)
    total = sum(weights)
    mean = sum(theta * w for theta, w in zip(_GRID, weights, strict=True)) / total
    variance = sum(
        (theta - mean) ** 2 * w for theta, w in zip(_GRID, weights, strict=True)
    )
    return AbilityEstimate(theta=mean, se=math.sqrt(variance / total))


def _confirms(estimate: AbilityEstimate, level: int) -> bool:
    if level == 0:
        return True
    return estimate.theta - CONFIDENCE_K * estimate.se >= GRADE_THRESHOLDS[level]


def retest_agreement(estimate: AbilityEstimate, level: int) -> float:
    """Вероятность, что повторная попытка на тот же грейд даст то же решение.

    Прогноз по апостериорному распределению: истинный θ ~ N(θ̂, SE²), у повторной попытки
    своя ошибка той же величины, поэтому её оценка ~ N(θ̂, 2·SE²). У самого порога это 50%:
    честно показывает, что решение там почти монетка при любом тесте.
    """
    if level == 0:
        return 1.0
    margin = estimate.theta - CONFIDENCE_K * estimate.se - GRADE_THRESHOLDS[level]
    # Φ(margin / (√2·SE)) через erf: Φ(x) = (1 + erf(x/√2)) / 2.
    passes_again = 0.5 * (1.0 + math.erf(margin / (2.0 * estimate.se)))
    return passes_again if margin >= 0 else 1.0 - passes_again


def decide_grade(estimate: AbilityEstimate, level: int) -> GradeDecision:
    """Итог попытки на уровень `level`."""
    estimated_level = max(
        lvl for lvl in range(MAX_LEVEL + 1) if _confirms(estimate, lvl)
    )
    return GradeDecision(
        passed=_confirms(estimate, level),
        strong=level < MAX_LEVEL and _confirms(estimate, level + 1),
        estimated_level=estimated_level,
        near_threshold=level > 0
        and abs(estimate.theta - GRADE_THRESHOLDS[level]) < estimate.se,
        retest_agreement=retest_agreement(estimate, level),
    )


def target_difficulty(level: int) -> float:
    """Сложность, вокруг которой собирается тест на уровень: чуть выше порога, где решается
    «подтвердил / нет»: там задания дают больше всего информации."""
    if level == 0:
        return -1.5
    return GRADE_THRESHOLDS[level] + 0.2
