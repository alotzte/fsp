"""Валидация механики тестирования на синтетических кандидатах.

Запуск: `uv run python -m validation.assessment > ../docs/validation-assessment.md`

Вызывает тот же код, что и сервис (сборка теста, продление у порога, генераторы заданий, IRT,
правило грейда), поэтому цифры относятся к реальной механике. Ответы кандидата с истинным
уровнем θ моделируются по 2PL с теми же параметрами a, b, что использует оценка.
Честное ограничение: a и b экспертные, поэтому симуляция подтверждает механику
(сопоставимость, стабильность, устойчивость к утечке), а не калибровку конкретных заданий.
Раздел про разброс сложности внутри семейства показывает, насколько цифры чувствительны
к этому допущению.
"""

import contextlib
import io
import math
import statistics
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from random import Random

from app.services.assessment.assembly import (
    BLUEPRINTS,
    EXTENSION_ITEMS,
    EXTENSION_ROUNDS,
    AssembledItem,
    AttemptScore,
    ScoredResponse,
    assemble,
    extend,
    extension_size,
    score_attempt,
)
from app.services.assessment.bank import FAMILIES, ItemKind, normalize_answer
from app.services.assessment.irt import (
    CONFIDENCE_K,
    GRADE_THRESHOLDS,
    PRIOR_SD,
    probability,
)

GRADES = ["Стажёр", "Junior", "Middle", "Senior", "Lead"]
# Диапазоны истинного θ для каждого уровня (между порогами).
BANDS = [(-2.5, -1.0), (-1.0, 0.0), (0.0, 1.0), (1.0, 1.8), (1.8, 2.8)]
PER_LEVEL = 300
# Корзины расстояния истинного θ до порога заявленного грейда.
DISTANCE_BINS = [(0.0, 0.25), (0.25, 0.5), (0.5, math.inf)]


def true_level(theta: float) -> int:
    return max([0] + [lvl for lvl, c in GRADE_THRESHOLDS.items() if theta >= c])


def take_test(
    items: list[AssembledItem],
    theta: float,
    rng: Random,
    known: Callable[[AssembledItem], str | None] = lambda _: None,
    shift: Callable[[], float] | None = None,
) -> list[ScoredResponse]:
    """Ответы кандидата: если ответ «известен» (утечка): подставляет его, иначе решает сам.
    shift: отклонение сложности экземпляра от сложности семейства (оценка его не знает)."""
    responses = []
    for it in items:
        leaked = known(it)
        b = it.family.b + (shift() if shift else 0.0)
        if leaked is not None:
            response = leaked
        elif rng.random() < probability(theta, it.family.a, b):
            response = it.item.answer
        else:
            response = "неверно"
        responses.append(
            ScoredResponse(it.family.a, it.family.b, it.item.answer, response)
        )
    return responses


@dataclass
class Run:
    items: list[AssembledItem]
    score: AttemptScore


def attempt(
    spec: str,
    level: int,
    theta: float,
    seed: int,
    recent: frozenset[str] = frozenset(),
    *,
    extend_near: bool = True,
    tau: float = 0.0,
) -> Run:
    """Попытка как в сервисе (backend: AssessmentService.finish): сборка, ответы, оценка и
    продление заданиями у порога, пока scoring его просит."""
    blueprint = BLUEPRINTS[spec]
    rng = Random(seed * 7 + 1)
    noise = Random(seed * 13 + 5)
    shift = (lambda: noise.gauss(0.0, tau)) if tau else None
    items = assemble(blueprint, level, seed, recent)
    responses = take_test(items, theta, rng, shift=shift)
    score = score_attempt(level, responses)
    extensions = 0
    while extend_near:
        count = extension_size(
            near_threshold=score.decision.near_threshold,
            extensions=extensions,
            express=False,
        )
        extra = (
            extend(blueprint, level, seed, count, {i.family.id for i in items}, recent)
            if count
            else []
        )
        if not extra:
            break
        items += extra
        responses += take_test(extra, theta, rng, shift=shift)
        score = score_attempt(level, responses)
        extensions += 1
    return Run(items, score)


def rudner(score: AttemptScore, level: int) -> float:
    """Индекс согласованности Руднера по одной попытке: p² + (1 − p)², где p: вероятность
    подтвердить грейд при θ = θ̂ с той же точностью. Так отчитываются экзамены, у которых нет
    повторных попыток."""
    if level == 0:
        return 1.0
    est = score.estimate
    z = (est.theta - CONFIDENCE_K * est.se - GRADE_THRESHOLDS[level]) / est.se
    p = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return p * p + (1 - p) * (1 - p)


@dataclass
class Summary:
    """Итоги прогона популяции: честная заявка, повтор и соседние грейды."""

    thetas: list[float] = field(default_factory=list)
    estimates: list[float] = field(default_factory=list)
    honest: Counter[int] = field(default_factory=Counter)
    count: Counter[int] = field(default_factory=Counter)
    over: Counter[int] = field(default_factory=Counter)
    under: Counter[int] = field(default_factory=Counter)
    same: list[bool] = field(default_factory=list)
    # По кандидатам без стажёров: (расстояние до порога, совпало ли решение при повторе).
    by_distance: list[tuple[float, bool]] = field(default_factory=list)
    rudner: list[float] = field(default_factory=list)
    lengths: list[int] = field(default_factory=list)

    def share(self, counter: Counter[int], level: int) -> float:
        return counter[level] / self.count[level]

    @property
    def retest(self) -> float:
        return statistics.fmean(self.same)

    @property
    def retest_graded(self) -> float:
        return statistics.fmean(same for _, same in self.by_distance)


def summarize(
    spec: str,
    people: list[tuple[int, float]],
    *,
    extend_near: bool = True,
    tau: float = 0.0,
    neighbors: bool = True,
) -> Summary:
    s = Summary()
    for n, (lvl, theta) in enumerate(people):
        first = attempt(spec, lvl, theta, n, extend_near=extend_near, tau=tau)
        recent = frozenset(i.family.id for i in first.items)
        second = attempt(
            spec, lvl, theta, 10_000 + n, recent, extend_near=extend_near, tau=tau
        )
        passed = first.score.decision.passed
        same = passed == second.score.decision.passed
        s.thetas.append(theta)
        s.estimates.append(first.score.estimate.theta)
        s.count[lvl] += 1
        s.honest[lvl] += passed
        s.same.append(same)
        s.lengths += [len(first.items), len(second.items)]
        if lvl > 0:
            s.by_distance.append((abs(theta - GRADE_THRESHOLDS[lvl]), same))
            s.rudner.append(rudner(first.score, lvl))
        if neighbors and lvl < 4:
            up = attempt(
                spec, lvl + 1, theta, 20_000 + n, extend_near=extend_near, tau=tau
            )
            s.over[lvl] += up.score.decision.passed
        if neighbors and lvl > 0:
            down = attempt(
                spec, lvl - 1, theta, 30_000 + n, extend_near=extend_near, tau=tau
            )
            s.under[lvl] += down.score.decision.passed
    return s


def uniform_population(rng: Random) -> list[tuple[int, float]]:
    return [
        (lvl, rng.uniform(*BANDS[lvl])) for lvl in range(5) for _ in range(PER_LEVEL)
    ]


def normal_population(rng: Random) -> list[tuple[int, float]]:
    """θ ~ N(0, 1), каждый заявляет свой истинный грейд: реалистичнее равномерной в
    диапазоне: у порогов людей меньше."""
    thetas = [rng.gauss(0.0, 1.0) for _ in range(5 * PER_LEVEL)]
    return [(true_level(t), t) for t in thetas]


def table(header: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def distance_rows(s: Summary) -> list[list[object]]:
    rows: list[list[object]] = []
    for low, high in DISTANCE_BINS:
        cell = [same for d, same in s.by_distance if low <= d < high]
        label = f"≥ {low}" if math.isinf(high) else f"{low}-{high}"
        rows.append(
            [label, pct(len(cell) / len(s.by_distance)), pct(statistics.fmean(cell))]
        )
    return rows


def accuracy_section(spec: str, s: Summary) -> str:
    r = statistics.correlation(s.thetas, s.estimates)
    rmse = math.sqrt(
        statistics.fmean(
            (a - b) ** 2 for a, b in zip(s.thetas, s.estimates, strict=True)
        )
    )
    base = BLUEPRINTS[spec].items_count
    extended = sum(length > base for length in s.lengths) / len(s.lengths)
    rows = [
        [
            GRADES[lvl],
            pct(s.share(s.honest, lvl)),
            pct(s.share(s.over, lvl)) if lvl < 4 else "-",
            pct(s.share(s.under, lvl)) if lvl > 0 else "-",
            f"{statistics.fmean(e for t, e in zip(s.thetas, s.estimates, strict=True) if true_level(t) == lvl):+.2f}",
        ]
        for lvl in range(5)
    ]
    return (
        f"### Направление `{spec}`\n\n"
        f"- Корреляция оценки θ̂ с истинным θ: **r = {r:.3f}**, RMSE = {rmse:.3f}\n"
        f"- Стабильность при повторе (другие задания, семейства первой попытки исключены): "
        f"**{pct(s.retest)}** совпадений решения «подтверждён / нет», без стажёров "
        f"(их грейд подтверждается всегда): **{pct(s.retest_graded)}**\n"
        f"- Индекс Руднера по одной попытке (без стажёров): {pct(statistics.fmean(s.rudner))}\n"
        f"- Длина: в среднем {statistics.fmean(s.lengths):.1f} заданий, максимум "
        f"{max(s.lengths)}; продлено {pct(extended)} попыток\n\n"
        + table(
            [
                "Истинный грейд",
                "Подтверждён при честной заявке",
                "Завышение: подтверждён грейд выше",
                "Подтверждён грейд ниже",
                "Средняя θ̂",
            ],
            rows,
        )
        + "\n\nСтабильность в зависимости от расстояния истинного θ до порога заявленного "
        "грейда (без стажёров):\n\n"
        + table(
            ["Расстояние до порога", "Доля кандидатов", "Стабильность"],
            distance_rows(s),
        )
    )


def normal_section(rng: Random) -> str:
    people = normal_population(rng)
    rows: list[list[object]] = []
    for spec in BLUEPRINTS:
        s = summarize(spec, people, neighbors=False)
        bins = distance_rows(s)
        rows.append(
            [f"`{spec}`", pct(s.retest), pct(s.retest_graded), *(b[2] for b in bins)]
        )
    return table(
        [
            "Направление",
            "Стабильность",
            "Без стажёров",
            *(f"Расстояние {b[0]}" for b in distance_rows(s)),
        ],
        rows,
    )


def ablation_section(
    spec: str, production: Summary, people: list[tuple[int, float]]
) -> str:
    """Что даёт продление у порога и как цифры зависят от разброса сложности экземпляров."""
    variants = [
        ("Механика сервиса", production),
        ("Без продления у порога", summarize(spec, people, extend_near=False)),
        ("Разброс сложности экземпляров τ = 0.2", summarize(spec, people, tau=0.2)),
        ("Разброс сложности экземпляров τ = 0.4", summarize(spec, people, tau=0.4)),
    ]
    rows = [
        [
            name,
            pct(s.retest_graded),
            f"{statistics.correlation(s.thetas, s.estimates):.3f}",
            pct(s.share(s.honest, 3)),
            pct(s.share(s.honest, 4)),
            pct(s.share(s.over, 3)),
            f"{statistics.fmean(s.lengths):.1f}",
        ]
        for name, s in variants
    ]
    return table(
        [
            "Вариант",
            "Стабильность (без стажёров)",
            "r(θ̂, θ)",
            "Честный Senior",
            "Честный Lead",
            "Завышение Senior → Lead",
            "Средняя длина",
        ],
        rows,
    )


# Сколько чужих попыток «лежит в базе» для детектора утечки.
FOREIGN_POOL = 20


def leak_section(spec: str, rng: Random) -> str:
    """Junior заявляет Middle, имея утёкшие ответы на долю L заданий."""
    level = 2
    juniors = [rng.uniform(*BANDS[1]) for _ in range(PER_LEVEL)]
    fixed_seed = 424242  # «единый набор»: у всех одни и те же экземпляры
    rows = []
    for share in (0.0, 0.25, 0.5, 0.75, 1.0):
        fixed_pass = families_pass = flagged = 0
        for n, theta in enumerate(juniors):
            leak_rng = Random(n)
            pool = {
                i.family.id: [i.item.answer]
                for i in assemble(BLUEPRINTS[spec], level, seed=90_000 + n)
            }
            for k in range(FOREIGN_POOL):
                for i in assemble(BLUEPRINTS[spec], level, seed=70_000 + k):
                    pool.setdefault(i.family.id, []).append(i.item.answer)
            # Единый набор: утёкший ответ всегда подходит.
            fixed_items = assemble(BLUEPRINTS[spec], level, fixed_seed)
            leaked_fixed = {
                i.family.id for i in fixed_items if leak_rng.random() < share
            }
            responses = take_test(
                fixed_items,
                theta,
                Random(n),
                lambda it, ids=leaked_fixed: (
                    it.item.answer if it.family.id in ids else None
                ),
            )
            fixed_pass += score_attempt(level, responses).decision.passed
            # Семейства: у кандидата свой экземпляр, утёк чужой (другой seed).
            own = assemble(BLUEPRINTS[spec], level, seed=50_000 + n)
            foreign = {
                i.family.id: i.item.answer
                for i in assemble(BLUEPRINTS[spec], level, seed=90_000 + n)
                if leak_rng.random() < share
            }
            responses = take_test(
                own, theta, Random(n), lambda it, f=foreign: f.get(it.family.id)
            )
            # Детектор сверяет текстовые ответы с эталонами чужих экземпляров в базе:
            # источник утечки плюс FOREIGN_POOL попыток других кандидатов.
            responses = [
                replace(r, foreign_answers=pool[it.family.id])
                if it.item.kind == ItemKind.TEXT
                else r
                for it, r in zip(own, responses, strict=True)
            ]
            result = score_attempt(level, responses)
            families_pass += result.decision.passed
            flagged += any(result.foreign_matches)
        rows.append(
            [
                pct(share),
                pct(fixed_pass / PER_LEVEL),
                pct(families_pass / PER_LEVEL),
                pct(flagged / PER_LEVEL),
            ]
        )
    return table(
        [
            "Доля утёкших ответов",
            "Единый набор заданий",
            "Семейства (наша механика)",
            "Помечены детектором утечки",
        ],
        rows,
    )


def collision_section() -> str:
    """Доля пар экземпляров одного семейства с одинаковым ответом: насколько утечка
    чужого экземпляра помогает. Высокая доля: слабое место, кандидат на переработку."""
    rows = []
    for family_id, fam in sorted(FAMILIES.items()):
        answers = [normalize_answer(fam.generate(Random(s)).answer) for s in range(200)]
        pairs = sum(c * (c - 1) for c in Counter(answers).values())
        rows.append(
            (pairs / (len(answers) * (len(answers) - 1)), family_id, fam.competency)
        )
    rows.sort(reverse=True)
    weak = [r for r in rows if r[0] >= 0.5]
    return (
        f"Семейств с совпадением ответов ≥ 50%: **{len(weak)} из {len(rows)}**.\n\n"
        + table(
            ["Семейство", "Компетенция", "Совпадение ответа у двух экземпляров"],
            [[fid, comp, pct(rate)] for rate, fid, comp in rows],
        )
    )


def executed_lines(code: str) -> int:
    """Сколько строк фрагмента выполнилось: прокси числа шагов решения «что выведет код»."""
    count = 0

    def tracer(frame, event, arg):
        nonlocal count
        if event == "line" and frame.f_code.co_filename == "<instance>":
            count += 1
        return tracer

    compiled = compile(code, "<instance>", "exec")
    sys.settrace(tracer)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compiled, {"__name__": "__main__"})  # noqa: S102  # только свои шаблоны
    finally:
        sys.settrace(None)
    return count


def size_section() -> str:
    """Инцидентальность параметров: у экземпляров одного семейства должен быть одинаковый
    объём работы. Прокси: число выполненных строк (Python) или строк кода/данных (остальные
    семейства с кодом). Коэффициент вариации выше 0.3: повод переработать генератор."""
    rows = []
    for family_id, fam in sorted(FAMILIES.items()):
        sizes = []
        for seed in range(100):
            item = fam.generate(Random(seed))
            if item.code is None:
                break
            if fam.competency == "python":
                sizes.append(executed_lines(item.code))
            else:
                sizes.append(
                    len([line for line in item.code.splitlines() if line.strip()])
                )
        if sizes:
            cv = statistics.pstdev(sizes) / statistics.fmean(sizes)
            rows.append((cv, family_id, statistics.fmean(sizes)))
    rows.sort(reverse=True)
    flagged = [r for r in rows if r[0] > 0.3]
    shown = [r for r in rows if r[0] >= 0.2]
    return (
        f"Семейств с кодом или данными: {len(rows)}; с коэффициентом вариации объёма > 0.3: "
        f"**{len(flagged)}**, ≥ 0.2: {len(shown)} (ниже), остальные однороднее.\n\n"
        + table(
            ["Семейство", "Средний объём", "Коэффициент вариации"],
            [[fid, f"{mean:.1f}", f"{cv:.2f}"] for cv, fid, mean in shown],
        )
    )


def main() -> None:
    rng = Random(2026)
    people = uniform_population(rng)
    print("# Валидация механики тестирования\n")
    print(
        f"Сгенерировано автоматически `scoring/validation/assessment.py`. "
        f"Синтетические кандидаты: {PER_LEVEL} на каждый из 5 грейдов, истинный θ равномерно "
        f"в диапазоне грейда. Правило: грейд подтверждён, если θ̂ − {CONFIDENCE_K}·SE ≥ порога; "
        f"θ̂: EAP с априорным N(0, {PRIOR_SD}²). Если порог ближе одной SE к оценке, попытка "
        f"продлевается на {EXTENSION_ITEMS} заданий у порога, не больше {EXTENSION_ROUNDS} раз. "
        f"Банк: {len(FAMILIES)} семейств.\n"
    )
    print("## Точность, завышение и стабильность\n")
    summaries = {}
    for spec in BLUEPRINTS:
        summaries[spec] = summarize(spec, people)
        print(accuracy_section(spec, summaries[spec]), "\n")
    print("## Стабильность в реалистичной популяции\n")
    print(
        "θ ~ N(0, 1), каждый заявляет свой истинный грейд. У порогов людей меньше, чем при "
        "равномерном распределении внутри грейда, поэтому общая стабильность выше; у самого "
        "порога решение остаётся почти монеткой при любом тесте.\n"
    )
    print(normal_section(Random(7)), "\n")
    print("## Абляции и чувствительность (`backend`)\n")
    print(
        "τ: стандартное отклонение сложности экземпляра от сложности семейства: ответы "
        "моделируются с b + N(0, τ²), а оценка, как в сервисе, знает только b семейства. "
        "Без данных пилота τ неизвестна; по литературе об автоматической генерации заданий "
        "разумный диапазон 0.2-0.4.\n"
    )
    print(ablation_section("backend", summaries["backend"], people), "\n")
    print("## Устойчивость к утечке заданий\n")
    print(
        "Junior заявляет Middle и знает ответы на долю L заданий из утечки. "
        "Показана доля таких кандидатов, получивших Middle, и доля помеченных детектором "
        "утечки: неверный ответ совпал с эталоном чужого экземпляра того же семейства "
        "(сверка с источником утечки и ещё 20 попытками в базе). Строка 0%: ложные "
        "срабатывания на честных кандидатах.\n"
    )
    for spec in BLUEPRINTS:
        print(f"### `{spec}`\n\n{leak_section(spec, Random(7))}\n")
    print("## Совпадение ответов внутри семейств\n")
    print(collision_section(), "\n")
    print("## Однородность экземпляров внутри семейства\n")
    print(size_section())


if __name__ == "__main__":
    main()
