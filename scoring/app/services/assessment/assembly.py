"""Сборка теста (LOFT: linear on the fly) и проверка ответов.

Каждому кандидату тест собирается заново по blueprint'у направления: квоты по компетенциям,
внутри квоты: случайные семейства из ближайших по сложности к целевому уровню
(randomesque: не самые информативные всегда, а случайные из окна, так задания
не «выгорают» от частого показа). Семейства из недавних попыток кандидата по возможности
исключаются, чтобы повтор не давал преимущества.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from random import Random

from app.services.assessment.bank import FAMILIES, Family, Item, normalize_answer
from app.services.assessment.irt import (
    GRADE_THRESHOLDS,
    AbilityEstimate,
    GradeDecision,
    ItemResponse,
    decide_grade,
    estimate_ability,
    target_difficulty,
)

# Сколько «лишних» кандидатов на место берётся в окно случайного выбора.
RANDOMESQUE_EXTRA = 3
# Продление у порога: если решение неуверенное (порог ближе одной SE к оценке θ), попытка
# получает задания со сложностью у порога: до EXTENSION_ROUNDS раз. Подобрано симуляцией
# (validation/assessment.py): стабильность при повторе растёт на 3-5 п.п., честный Senior и Lead
# подтверждаются в ~70% попыток вместо 55% и 41%; в среднем тест длиннее на 3 задания.
EXTENSION_ROUNDS = 2
EXTENSION_ITEMS = 5
EXPRESS_EXTENSION_ITEMS = 3

COMPETENCY_TITLES = {
    "python": "Python",
    "sql": "SQL и базы данных",
    "algorithms": "Алгоритмы и структуры данных",
    "http_api": "HTTP и API",
    "js": "JavaScript",
    "web": "HTML, CSS и браузер",
    "react": "React",
    "ml": "Машинное обучение",
    "stats": "Статистика",
}


@dataclass(frozen=True)
class Blueprint:
    specialization: str
    quotas: dict[str, int]
    time_limit_minutes: int

    @property
    def items_count(self) -> int:
        return sum(self.quotas.values())


# Ключ: slug специализации из справочника backend.
BLUEPRINTS: dict[str, Blueprint] = {
    blueprint.specialization: blueprint
    for blueprint in [
        # 15 заданий: при 10 стабильность грейда при повторе ~70%, при 15: ~75%
        # (scoring/validation/assessment.py). Дальше рост медленный, а время теста растёт.
        Blueprint(
            "backend", {"python": 4, "sql": 4, "algorithms": 4, "http_api": 3}, 25
        ),
        Blueprint("frontend", {"js": 6, "web": 3, "react": 3, "http_api": 3}, 25),
        Blueprint("data-science", {"python": 3, "ml": 4, "stats": 4, "sql": 4}, 25),
    ]
}


def shortened(blueprint: Blueprint, length: int) -> Blueprint:
    """Короткая версия теста (экспресс для демо): те же компетенции в тех же пропорциях,
    у каждой хотя бы одно задание."""
    if length >= blueprint.items_count:
        return blueprint
    total = blueprint.items_count
    quotas = {c: max(1, n * length // total) for c, n in blueprint.quotas.items()}
    # Добираем недостающие задания компетенциям с наибольшим остатком.
    by_remainder = sorted(
        blueprint.quotas,
        key=lambda c: (blueprint.quotas[c] * length) % total,
        reverse=True,
    )
    for competency in by_remainder:
        if sum(quotas.values()) >= length:
            break
        quotas[competency] += 1
    # Минута на задание: экспресс-тест укладывается в 3-6 минут, как просили организаторы.
    return Blueprint(blueprint.specialization, quotas, sum(quotas.values()))


@dataclass(frozen=True)
class AssembledItem:
    family: Family
    item: Item


def select_families(
    blueprint: Blueprint, level: int, rng: Random, recent_families: Collection[str] = ()
) -> list[Family]:
    target = target_difficulty(level)
    selected: list[Family] = []
    for competency, count in blueprint.quotas.items():
        pool = sorted(
            (f for f in FAMILIES.values() if f.competency == competency),
            key=lambda f: abs(f.b - target),
        )
        fresh = [f for f in pool if f.id not in recent_families]
        used = [f for f in pool if f.id in recent_families]
        window = fresh[: count + RANDOMESQUE_EXTRA]
        picked = rng.sample(window, min(count, len(window)))
        # Свежих не хватило (маленький банк): добираем ближайшими из недавних.
        picked += used[: count - len(picked)]
        selected += sorted(picked, key=lambda f: f.b)
    return selected


def assemble(
    blueprint: Blueprint, level: int, seed: int, recent_families: Collection[str] = ()
) -> list[AssembledItem]:
    """Детерминированно по seed: одна попытка всегда пересобирается в те же задания."""
    families = select_families(blueprint, level, Random(seed), recent_families)
    return [
        AssembledItem(family, family.generate(Random(f"{seed}:{family.id}")))
        for family in families
    ]


def weekly_case(blueprint: Blueprint, level: int, seed: int) -> AssembledItem:
    """Одно задание направления у сложности уровня: «кейс недели». Компетенция выбирается
    по квотам blueprint'а, семейство как при сборке теста, случайное из ближайших по
    сложности. Экземпляр свой у каждого seed, поэтому кейс не подсказывает ответы теста."""
    rng = Random(seed)
    competency = rng.choices(
        list(blueprint.quotas), weights=list(blueprint.quotas.values())
    )[0]
    (family,) = select_families(
        Blueprint(blueprint.specialization, {competency: 1}, 1), level, rng
    )
    return AssembledItem(family, family.generate(Random(f"{seed}:{family.id}")))


def extension_size(*, near_threshold: bool, extensions: int, express: bool) -> int:
    """Сколько заданий добавить к попытке перед решением о грейде (0: решать сейчас).

    У самого порога решение «подтверждён / нет» почти монетка, а задания со сложностью у
    порога уточняют его сильнее всего. Число продлений ограничено, чтобы тест не рос без
    конца: у кого и после них решение у порога, тот получает результат с низкой устойчивостью.
    """
    if not near_threshold or extensions >= EXTENSION_ROUNDS:
        return 0
    return EXPRESS_EXTENSION_ITEMS if express else EXTENSION_ITEMS


def extend(
    blueprint: Blueprint,
    level: int,
    seed: int,
    count: int,
    attempt_families: Collection[str],
    recent_families: Collection[str] = (),
) -> list[AssembledItem]:
    """Задания продления попытки, когда решение у порога неуверенное.

    Берутся семейства направления, ближайшие по сложности к порогу грейда: именно там
    решается «подтвердил / нет», и задание даёт больше всего информации. Показанные в этой
    попытке не повторяются, семейства недавних попыток берутся, только если свежих не хватило.
    Экземпляры, как и при сборке, детерминированы seed попытки.
    """
    threshold = GRADE_THRESHOLDS[level]
    pool = sorted(
        (
            f
            for f in FAMILIES.values()
            if f.competency in blueprint.quotas and f.id not in attempt_families
        ),
        key=lambda f: (f.id in recent_families, abs(f.b - threshold)),
    )
    return [
        AssembledItem(f, f.generate(Random(f"{seed}:{f.id}"))) for f in pool[:count]
    ]


def is_correct(answer: str, response: str | None) -> bool:
    """Сверка с эталоном без придирок к записи: запятая бывает и десятичной («0,42»), и разделителем
    списка («3,4,7»); «12.0» = «12»; кавычки вокруг ответа не важны."""
    if response is None:
        return False
    expected = normalize_answer(answer)
    unquoted = response.strip().strip("\"'«»“”")
    as_list = " ".join(unquoted.lower().replace(",", " ").split())
    given = normalize_answer(unquoted)
    if expected in (given, as_list):
        return True
    try:
        return float(expected) == float(given)
    except ValueError:
        return False


@dataclass(frozen=True)
class ScoredResponse:
    a: float
    b: float
    answer: str
    response: str | None
    # Эталоны других экземпляров того же семейства: для детектора утечки.
    foreign_answers: Sequence[str] = ()


@dataclass(frozen=True)
class AttemptScore:
    correct: list[bool]
    estimate: AbilityEstimate
    decision: GradeDecision
    # Ответ не подошёл к своему экземпляру, но совпал с эталоном чужого: признак утечки.
    foreign_matches: list[bool]


def matches_foreign(answer: str, response: str | None, foreign: Iterable[str]) -> bool:
    """Неверный ответ, совпавший с эталоном другого экземпляра того же семейства, почти
    наверняка списан из утечки: сам по себе такой ответ получить трудно. Совпадение с эталоном,
    равным своему, утечкой не считается: тогда ответ просто верный."""
    return not is_correct(answer, response) and any(
        is_correct(f, response) for f in foreign
    )


def score_attempt(level: int, responses: Sequence[ScoredResponse]) -> AttemptScore:
    correct = [is_correct(r.answer, r.response) for r in responses]
    estimate = estimate_ability(
        [ItemResponse(r.a, r.b, ok) for r, ok in zip(responses, correct, strict=True)]
    )
    foreign = [
        matches_foreign(r.answer, r.response, r.foreign_answers) for r in responses
    ]
    return AttemptScore(correct, estimate, decide_grade(estimate, level), foreign)
