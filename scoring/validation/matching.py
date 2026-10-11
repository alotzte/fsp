"""Валидация подбора на синтетических потребностях и кандидатах с известной релевантностью.

Запуск: `uv run python -m validation.matching > ../docs/validation-matching.md`

Модель данных:
- у кандидата есть истинный уровень θ и истинные навыки; в резюме он перечисляет истинные
  навыки плюс «для красоты» ещё несколько (самоописание шумит: ровно проблема из ТЗ);
- грейд кандидата определяется настоящим тестом (сборка в scoring, ответы по 2PL от θ),
  часть кандидатов тест не проходила: у них только заявленный грейд;
- истинная релевантность пары «потребность и кандидат» (0-3) считается по истинному уровню,
  истинным навыкам, формату и совместимости вилки: система её не видит.

Сравниваем: случайный порядок (нижняя граница), только заявленный грейд, поиск по ключевым
словам резюме и BM25 по тексту резюме (как на универсальных площадках), наш подбор без
результатов теста и полный подбор. Каждая строка добавляет один слой, поэтому видно, что даёт
каждый. Метрики: P@5, P@10 (доля релевантных в топе: так ТЗ формулирует проверку), nDCG@10
с бутстреп-интервалом по потребностям, MRR и Recall@20; fairness: доля кандидатов без ФСП
в топ-10 против их доли в пуле.

«Слепой» генератор (раздел в конце отчёта) убирает преимущество по построению: навыки в резюме
написаны названием, синонимом из словаря или перефразом вне словаря («питон», «Postgres 16»);
матчер видит только то, что разрешилось через словарь по тому же правилу, что
`DictionaryService.resolve_skills` в backend. Часть кандидатов набивает резюме ключевыми словами.
Релевантность считается по скрытым истинным навыкам.
"""

import math
import re
import statistics
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from random import Random

from app.services.assessment.assembly import BLUEPRINTS
from app.services.assessment.irt import GRADE_THRESHOLDS
from app.services.matching import CandidateFeatures, Need, NeedSkill, rank
from validation.assessment import attempt

NEEDS = 40
POOL = 60
BANDS = [(-2.5, -1.0), (-1.0, 0.0), (0.0, 1.0), (1.0, 1.8), (1.8, 2.8)]
GRADE_TITLES = ["Стажёр", "Junior", "Middle", "Senior", "Lead"]
SKILLS = list(range(1, 21))
FORMATS = ["office", "hybrid", "remote"]
SALARY_K = {0: (50, 80), 1: (90, 150), 2: (170, 280), 3: (290, 450), 4: (400, 600)}
TESTED_SHARE = 0.8
# Доля кандидатов, заявляющих грейд выше истинного. Её никто не знает, поэтому результаты
# приводятся для нескольких значений.
OVERCLAIM_SHARES = (0.0, 0.25, 0.5)
PADDING_SKILLS = (1, 4)
RELEVANT = 2
FSP_SHARE = 0.4
BOOTSTRAP = 1000

# Навыки слепого генератора: название и синонимы есть в словаре матчера, перефразы: нет.
VOCAB: dict[int, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    1: ("Python", ("py", "python3"), ("питон", "Python 3.12")),
    2: ("Go", ("golang",), ("Go-сервисы", "гошка")),
    3: ("Java", (), ("Java 17", "джава")),
    4: ("PostgreSQL", ("postgres",), ("Postgres 16", "постгрес")),
    5: ("Kubernetes", ("k8s",), ("кубер", "K8s-кластеры")),
    6: ("Docker", (), ("докер", "Docker Compose")),
    7: ("Kafka", ("apache kafka",), ("кафка", "Kafka Streams")),
    8: ("Redis", (), ("редис", "Redis Cluster")),
    9: ("React", ("react.js", "reactjs"), ("реакт", "React 18")),
    10: ("TypeScript", ("ts",), ("тайпскрипт", "TS 5")),
    11: ("SQL", (), ("SQL-запросы", "оконные функции")),
    12: ("Linux", (), ("линукс", "Ubuntu Server")),
    13: ("Git", (), ("гит", "GitLab Flow")),
    14: ("FastAPI", (), ("фастапи", "FastAPI + Pydantic")),
    15: ("Django", (), ("джанго", "Django REST")),
    16: ("Pandas", ("pandas",), ("пандас", "датафреймы")),
    17: ("PyTorch", ("torch",), ("пайторч", "нейросети на torch")),
    18: ("ClickHouse", ("clickhouse",), ("кликхаус", "ClickHouse-кластер")),
    19: ("gRPC", ("grpc",), ("protobuf/gRPC", "грпц")),
    20: ("CI/CD", ("ci-cd",), ("GitLab CI", "пайплайны")),
}
# Как написан истинный навык: название, синоним, перефраз вне словаря.
SPELLING_WEIGHTS = (0.5, 0.25, 0.25)
STUFFER_SHARE = 0.3
STUFFING = (6, 10)


@dataclass(frozen=True)
class Candidate:
    features: CandidateFeatures
    true_level: int
    true_skills: frozenset[int]
    # Текст резюме из навыков и заявленного грейда: по нему ищут бейзлайны «как на площадке».
    resume: str = ""


def resolve(mentions: Sequence[str]) -> frozenset[int]:
    """Как `DictionaryService.resolve_skills`: точное совпадение с названием или синонимом без
    учёта регистра; всё остальное: свой тег, матчер его не видит."""
    by_name = {
        name.casefold(): skill_id
        for skill_id, (title, aliases, _) in VOCAB.items()
        for name in (title, *aliases)
    }
    return frozenset(by_name[m.casefold()] for m in mentions if m.casefold() in by_name)


def spell(skill_id: int, rng: Random) -> str:
    title, aliases, paraphrases = VOCAB[skill_id]
    kind = rng.choices(range(3), weights=SPELLING_WEIGHTS)[0]
    if kind == 1 and aliases:
        return rng.choice(aliases)
    if kind == 2:
        return rng.choice(paraphrases)
    return title


def true_level(theta: float) -> int:
    return max([0] + [lvl for lvl, c in GRADE_THRESHOLDS.items() if theta >= c])


def make_candidate(
    key: int, spec: str, rng: Random, overclaim: float, *, blind: bool = False
) -> Candidate:
    level = rng.choices(range(5), weights=[1, 3, 4, 3, 1])[0]
    theta = rng.uniform(*BANDS[level])
    true_skills = frozenset(rng.sample(SKILLS, rng.randint(3, 8)))
    stuffer = blind and rng.random() < STUFFER_SHARE
    padding = frozenset(
        rng.sample(SKILLS, rng.randint(*(STUFFING if stuffer else PADDING_SKILLS)))
    )
    claimed = min(4, level + (1 if rng.random() < overclaim else 0))
    if blind:
        # Истинные навыки пишутся как попало; набивка идёт названиями, её цель попасть в фильтры.
        mentions = [spell(s, rng) for s in sorted(true_skills)]
        mentions += [VOCAB[s][0] for s in sorted(padding - true_skills)]
    else:
        mentions = [VOCAB[s][0] for s in sorted(true_skills | padding)]
    has_fsp = rng.random() < FSP_SHARE
    features = CandidateFeatures(
        key=key,
        grade_level=claimed,
        grade_title=GRADE_TITLES[claimed],
        confirmed=False,
        skills=resolve(mentions),
        work_formats=frozenset(rng.sample(FORMATS, rng.randint(1, 3))),
        salary_expectation=rng.randint(*SALARY_K[level]) * 1000,
        # ФСП не зависит от релевантности: худший случай для fairness.
        fsp_score=rng.uniform(0.2, 0.9) if has_fsp else 0.0,
        fsp_achievements=rng.randint(1, 3) if has_fsp else 0,
    )
    resume = f"{GRADE_TITLES[claimed]}. Навыки: {', '.join(mentions)}"
    if rng.random() < TESTED_SHARE:
        # Попытка как в сервисе, с продлением у порога (validation/assessment.py).
        result = attempt(spec, claimed, theta, seed=key).score
        if result.decision.passed:
            features = replace(
                features,
                confirmed=True,
                theta=result.estimate.theta,
                theta_se=result.estimate.se,
            )
        else:
            # Не подтвердил заявленный грейд: в категории остаётся заявленный без подтверждения,
            # но оценка уровня из попытки сохраняется: как в backend (candidate_grades.theta).
            features = replace(
                features, theta=result.estimate.theta, theta_se=result.estimate.se
            )
    return Candidate(features, true_level(theta), true_skills, resume)


def make_need(rng: Random) -> Need:
    level = rng.choice([1, 2, 2, 3, 3, 4])
    skills = rng.sample(SKILLS, rng.randint(2, 4))
    must = rng.randint(1, len(skills))
    _, high = SALARY_K[level]
    return Need(
        grade_level=level,
        skills=[NeedSkill(s, VOCAB[s][0], i < must) for i, s in enumerate(skills)],
        work_formats=frozenset(rng.sample(FORMATS, rng.randint(1, 2))),
        salary_to=high * 1000,
    )


def relevance(need: Need, c: Candidate) -> int:
    """Истинная релевантность 0-3: по истинным уровню и навыкам, которых система не видит."""
    f = c.features
    if (
        f.salary_expectation is not None
        and need.salary_to is not None
        and f.salary_expectation > need.salary_to
    ):
        return 0
    if need.work_formats and not need.work_formats & f.work_formats:
        return 0
    assert need.grade_level is not None
    distance = abs(c.true_level - need.grade_level)
    missing = sum(1 for s in need.skills if s.must_have and s.id not in c.true_skills)
    if distance == 0 and missing == 0:
        return 3
    if distance + missing == 1:
        return 2
    if distance + missing == 2:
        return 1
    return 0


def random_rank(need: Need, pool: Sequence[Candidate]) -> list[int]:
    """Нижняя граница: P@k ≈ доле релевантных в пуле. Seed от пула: отчёт воспроизводим."""
    keys = [c.features.key for c in pool]
    Random(keys[0]).shuffle(keys)
    return keys


def grade_only_rank(need: Need, pool: Sequence[Candidate]) -> list[int]:
    """Только категория: чем ближе заявленный грейд, тем выше, навыки и тест не учитываются."""
    assert need.grade_level is not None
    level = need.grade_level

    def distance(c: Candidate) -> int:
        grade = c.features.grade_level
        return abs(grade - level) if grade is not None else 99

    return [c.features.key for c in sorted(pool, key=distance)]


def keyword_rank(need: Need, pool: Sequence[Candidate]) -> list[int]:
    """Бейзлайн универсальной площадки: вхождение названий навыков в текст резюме и совпадение
    заявленного грейда."""

    def score(c: Candidate) -> tuple[int, int]:
        text = c.resume.casefold()
        hits = sum(1 for s in need.skills if s.title.casefold() in text)
        return hits, int(c.features.grade_level == need.grade_level)

    return [c.features.key for c in sorted(pool, key=score, reverse=True)]


_TOKEN = re.compile(r"[\w+#./-]+")
BM25_K1, BM25_B = 1.2, 0.75


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


def bm25_rank(need: Need, pool: Sequence[Candidate]) -> list[int]:
    """BM25 по тексту резюме: запрос: навыки потребности (обязательные дважды) и грейд."""
    assert need.grade_level is not None
    query = [
        t for s in need.skills for t in _tokens(s.title) * (2 if s.must_have else 1)
    ]
    query += _tokens(GRADE_TITLES[need.grade_level])
    docs = [_tokens(c.resume) for c in pool]
    average = statistics.fmean(len(d) for d in docs)
    frequency = Counter(t for d in docs for t in set(d))

    def score(doc: list[str]) -> float:
        counts = Counter(doc)
        total = 0.0
        for term in query:
            if term not in counts:
                continue
            idf = math.log(
                1 + (len(docs) - frequency[term] + 0.5) / (frequency[term] + 0.5)
            )
            tf = counts[term]
            norm = tf + BM25_K1 * (1 - BM25_B + BM25_B * len(doc) / average)
            total += idf * tf * (BM25_K1 + 1) / norm
        return total

    scores = {c.features.key: score(d) for c, d in zip(pool, docs, strict=True)}
    return sorted(scores, key=lambda key: scores[key], reverse=True)


def ours(need: Need, pool: Sequence[Candidate], *, use_test: bool = True) -> list[int]:
    features = [
        c.features if use_test else replace(c.features, confirmed=False, theta=None)
        for c in pool
    ]
    return [m.key for m in rank(need, features)]


def precision(
    ranked: Sequence[int], rel: dict[int, int], k: int, threshold: int = RELEVANT
) -> float:
    return sum(1 for key in ranked[:k] if rel[key] >= threshold) / k


def ndcg(ranked: Sequence[int], rel: dict[int, int], k: int = 10) -> float:
    def dcg(values: Sequence[int]) -> float:
        return sum((2**v - 1) / math.log2(i + 2) for i, v in enumerate(values[:k]))

    ideal = dcg(sorted(rel.values(), reverse=True))
    return dcg([rel[key] for key in ranked]) / ideal if ideal else 0.0


def reciprocal_rank(ranked: Sequence[int], rel: dict[int, int]) -> float:
    return next(
        (1 / (i + 1) for i, key in enumerate(ranked) if rel[key] >= RELEVANT), 0.0
    )


def recall(ranked: Sequence[int], rel: dict[int, int], k: int = 20) -> float:
    relevant = sum(1 for value in rel.values() if value >= RELEVANT)
    return (
        sum(1 for key in ranked[:k] if rel[key] >= RELEVANT) / relevant
        if relevant
        else 1.0
    )


def bootstrap_ci(values: Sequence[float], seed: int = 2026) -> tuple[float, float]:
    """95% интервал среднего по потребностям (перевыборка потребностей)."""
    rng = Random(seed)
    means = sorted(
        statistics.fmean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP)
    )
    return means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP) - 1]


@dataclass(frozen=True)
class Scores:
    p5: float
    p10: float
    ndcg10: float
    ndcg_ci: tuple[float, float]
    exact5: float
    mrr: float
    recall20: float
    # Доля кандидатов без ФСП в топ-10 и в пуле.
    no_fsp_top10: float
    no_fsp_pool: float


def evaluate(
    method: Callable[[Need, Sequence[Candidate]], list[int]],
    cases: Sequence[tuple[Need, list[Candidate]]],
) -> Scores:
    rows: dict[str, list[float]] = {
        k: [] for k in ("p5", "p10", "n10", "exact5", "mrr", "r20", "top", "pool")
    }
    for need, pool in cases:
        rel = {c.features.key: relevance(need, c) for c in pool}
        no_fsp = {c.features.key for c in pool if c.features.fsp_score == 0}
        ranked = method(need, pool)
        rows["p5"].append(precision(ranked, rel, 5))
        rows["p10"].append(precision(ranked, rel, 10))
        rows["n10"].append(ndcg(ranked, rel))
        rows["exact5"].append(precision(ranked, rel, 5, threshold=3))
        rows["mrr"].append(reciprocal_rank(ranked, rel))
        rows["r20"].append(recall(ranked, rel))
        rows["top"].append(sum(1 for key in ranked[:10] if key in no_fsp) / 10)
        rows["pool"].append(len(no_fsp) / len(pool))
    mean = {k: statistics.fmean(v) for k, v in rows.items()}
    return Scores(
        p5=mean["p5"],
        p10=mean["p10"],
        ndcg10=mean["n10"],
        ndcg_ci=bootstrap_ci(rows["n10"]),
        exact5=mean["exact5"],
        mrr=mean["mrr"],
        recall20=mean["r20"],
        no_fsp_top10=mean["top"],
        no_fsp_pool=mean["pool"],
    )


def build_cases(
    seed: int, overclaim: float, *, blind: bool = False
) -> list[tuple[Need, list[Candidate]]]:
    rng = Random(seed)
    cases = []
    key = 0
    for n in range(NEEDS):
        spec = list(BLUEPRINTS)[n % len(BLUEPRINTS)]
        need = make_need(rng)
        pool = []
        for _ in range(POOL):
            key += 1
            pool.append(make_candidate(key, spec, rng, overclaim, blind=blind))
        cases.append((need, pool))
    return cases


METHODS: dict[str, Callable[[Need, Sequence[Candidate]], list[int]]] = {
    "Случайный порядок (бейзлайн)": random_rank,
    "Только заявленный грейд (бейзлайн)": grade_only_rank,
    "Ключевые слова резюме (бейзлайн)": keyword_rank,
    "BM25 по тексту резюме (бейзлайн)": bm25_rank,
    "Наш подбор без результатов теста": lambda need, pool: ours(
        need, pool, use_test=False
    ),
    "Наш подбор (полный)": ours,
}


TABLE_HEADER = (
    "| Метод | P@5 | P@10 | nDCG@10 [95% ДИ] | MRR | Recall@20 | P@5 точное попадание |\n"
    "|---|---|---|---|---|---|---|"
)


def print_table(cases: Sequence[tuple[Need, list[Candidate]]]) -> Scores:
    share = statistics.fmean(
        sum(1 for c in pool if relevance(need, c) >= RELEVANT) / len(pool)
        for need, pool in cases
    )
    print(f"Релевантных в пуле в среднем {100 * share:.0f}%.\n")
    print(TABLE_HEADER)
    full = None
    for name, method in METHODS.items():
        s = evaluate(method, cases)
        low, high = s.ndcg_ci
        print(
            f"| {name} | {s.p5:.3f} | {s.p10:.3f} | {s.ndcg10:.3f} [{low:.3f}; {high:.3f}] "
            f"| {s.mrr:.3f} | {s.recall20:.3f} | {s.exact5:.3f} |"
        )
        full = s
    print()
    assert full is not None
    return full


def main() -> None:
    print("# Валидация подбора\n")
    print(
        "Сгенерировано автоматически `scoring/validation/matching.py`. "
        f"{NEEDS} потребностей × {POOL} кандидатов; релевантен кандидат с истинной "
        f"релевантностью ≥ {RELEVANT} из 3. Самоописание шумит: в резюме к истинным навыкам "
        f"добавлено 1-4 лишних; {int(100 * TESTED_SHARE)}% кандидатов прошли тест, "
        f"у {int(100 * FSP_SHARE)}% есть результаты ФСП (независимо от релевантности). Доля "
        "завышающих грейд неизвестна, поэтому результаты: для нескольких её значений. "
        "ДИ: бутстреп по потребностям.\n"
    )
    fairness = []
    for overclaim in OVERCLAIM_SHARES:
        print(f"## Завышают грейд {int(100 * overclaim)}% кандидатов\n")
        full = print_table(build_cases(2026, overclaim))
        fairness.append((f"обычный, завышают {int(100 * overclaim)}%", full))

    blind_overclaim = 0.25
    print(f"## Слепой генератор (завышают грейд {int(100 * blind_overclaim)}%)\n")
    print(
        f"Истинный навык написан названием ({int(100 * SPELLING_WEIGHTS[0])}%), синонимом из "
        f"словаря ({int(100 * SPELLING_WEIGHTS[1])}%) или перефразом вне словаря "
        f"({int(100 * SPELLING_WEIGHTS[2])}%: «питон», «Postgres 16»: матчер их не видит). "
        f"{int(100 * STUFFER_SHARE)}% кандидатов набивают резюме: {STUFFING[0]}-{STUFFING[1]} "
        "лишних навыков названиями из словаря. Релевантность: по скрытым истинным навыкам.\n"
    )
    full = print_table(build_cases(2027, blind_overclaim, blind=True))
    fairness.append((f"слепой, завышают {int(100 * blind_overclaim)}%", full))

    print("## Fairness: кандидаты без ФСП\n")
    print(
        "Доля кандидатов без истории ФСП в топ-10 полного подбора против их доли в пуле. "
        "ФСП в генераторе не связан с релевантностью, поэтому это верхняя оценка перекоса: "
        "вклад ФСП (вес 0.10) поднимает кандидатов с ФСП при прочих равных.\n"
    )
    print("| Генератор | В пуле | В топ-10 |\n|---|---|---|")
    for name, s in fairness:
        print(f"| {name} | {100 * s.no_fsp_pool:.0f}% | {100 * s.no_fsp_top10:.0f}% |")


if __name__ == "__main__":
    main()
