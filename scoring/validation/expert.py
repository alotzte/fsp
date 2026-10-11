"""Экспертная разметка пар «потребность и кандидат» (критерий 2: «соответствие экспертной оценке»).

Два шага:

1. `uv run python -m validation.expert sample`: 40 пар из слепого генератора
   (`validation.matching`): по 5 кандидатов на 8 потребностей, 3 из топа нашего подбора и 2 случайных,
   в перемешанном порядке и без скора системы. Пишет `docs/expert/pairs.csv` для разметки и
   `docs/expert/key.csv` с позицией в подборе и скрытой релевантностью: его разметчикам не открывать.
2. Двое из команды **независимо** ставят каждой паре оценку 0-3 в колонки `rater_a` и `rater_b`
   (3: пригласил бы сразу, 2: подходит с оговорками, 1: скорее нет, 0: нет). Видят только то,
   что видит работодатель: резюме, заявленный грейд, подтверждение тестом, форматы, ФСП.
3. `uv run python -m validation.expert report`: каппа Коэна (взвешенная квадратично, шкала
   порядковая), nDCG@5 и попадание лучшего кандидата нашего подбора против средней экспертной оценки,
   согласие экспертов со скрытой релевантностью генератора. Пишет `docs/validation-expert.md`.

Пока разметки нет, отчёта нет: цифры, которых никто не ставил, были бы выдумкой.
"""

import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from random import Random

from validation.matching import (
    GRADE_TITLES,
    Candidate,
    build_cases,
    ours,
    relevance,
)

ROOT = Path(__file__).resolve().parents[2]
PAIRS = ROOT / "docs" / "expert" / "pairs.csv"
# Ключ: позиция в подборе и скрытая релевантность генератора. Разметчикам не открывать.
KEY = ROOT / "docs" / "expert" / "key.csv"
REPORT = ROOT / "docs" / "validation-expert.md"
NEEDS = 8
TOP = 3
RANDOM = 2
SCALE = 4  # оценки 0..3
FORMAT_TITLES = {"office": "офис", "hybrid": "гибрид", "remote": "удалёнка"}
FIELDS = ["pair_id", "need", "candidate", "rater_a", "rater_b"]
KEY_FIELDS = ["pair_id", "truth", "rank"]


def _need_text(need) -> str:
    must = ", ".join(s.title for s in need.skills if s.must_have)
    nice = ", ".join(s.title for s in need.skills if not s.must_have)
    formats = ", ".join(FORMAT_TITLES[f] for f in sorted(need.work_formats))
    parts = [f"Грейд {GRADE_TITLES[need.grade_level]}", f"обязательно: {must}"]
    if nice:
        parts.append(f"желательно: {nice}")
    parts += [f"формат: {formats}", f"вилка до {need.salary_to // 1000} тыс. ₽"]
    return "; ".join(parts)


def _candidate_text(c: Candidate) -> str:
    f = c.features
    confirmed = "подтверждён тестом" if f.confirmed else "не подтверждён"
    formats = ", ".join(FORMAT_TITLES[x] for x in sorted(f.work_formats))
    fsp = f"; ФСП: {f.fsp_achievements} достижения" if f.fsp_achievements else ""
    salary = (
        f"; ожидания от {f.salary_expectation // 1000} тыс. ₽"
        if f.salary_expectation
        else ""
    )
    return f"{c.resume}; грейд {confirmed}; формат: {formats}{salary}{fsp}"


def sample() -> None:
    rng = Random(2026)
    rows = []
    for n, (need, pool) in enumerate(build_cases(2027, 0.25, blind=True)[:NEEDS]):
        ranked = ours(need, pool)
        by_key = {c.features.key: c for c in pool}
        chosen = ranked[:TOP] + rng.sample(ranked[TOP:], RANDOM)
        rng.shuffle(chosen)
        for key in chosen:
            c = by_key[key]
            rows.append(
                {
                    "pair_id": f"{n + 1}-{len(rows) % (TOP + RANDOM) + 1}",
                    "need": f"Потребность {n + 1}: {_need_text(need)}",
                    "candidate": _candidate_text(c),
                    "rater_a": "",
                    "rater_b": "",
                    "truth": relevance(need, c),
                    "rank": ranked.index(key) + 1,
                }
            )
    PAIRS.parent.mkdir(parents=True, exist_ok=True)
    for path, fields in ((PAIRS, FIELDS), (KEY, KEY_FIELDS)):
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    print(f"{len(rows)} пар → {PAIRS.relative_to(ROOT)}")


def weighted_kappa(a: list[int], b: list[int]) -> float:
    """Каппа Коэна с квадратичными весами: несогласие 0 и 3 хуже, чем 2 и 3."""
    n = len(a)
    observed = [[0.0] * SCALE for _ in range(SCALE)]
    for x, y in zip(a, b, strict=True):
        observed[x][y] += 1 / n
    pa = [a.count(i) / n for i in range(SCALE)]
    pb = [b.count(i) / n for i in range(SCALE)]
    weight = [
        [(i - j) ** 2 / (SCALE - 1) ** 2 for j in range(SCALE)] for i in range(SCALE)
    ]
    num = sum(weight[i][j] * observed[i][j] for i in range(SCALE) for j in range(SCALE))
    den = sum(weight[i][j] * pa[i] * pb[j] for i in range(SCALE) for j in range(SCALE))
    return 1 - num / den if den else 1.0


def _ndcg(order: list[float]) -> float:
    def dcg(values: list[float]) -> float:
        return sum((2**v - 1) / math.log2(i + 2) for i, v in enumerate(values))

    ideal = dcg(sorted(order, reverse=True))
    return dcg(order) / ideal if ideal else 1.0


def report() -> None:
    with KEY.open(encoding="utf-8") as file:
        key = {r["pair_id"]: r for r in csv.DictReader(file)}
    with PAIRS.open(encoding="utf-8") as file:
        rows = [
            r
            | {"_truth": key[r["pair_id"]]["truth"], "_rank": key[r["pair_id"]]["rank"]}
            for r in csv.DictReader(file)
            if r["rater_a"] and r["rater_b"]
        ]
    if not rows:
        sys.exit("Разметки нет: заполните rater_a и rater_b в docs/expert/pairs.csv")
    a = [int(r["rater_a"]) for r in rows]
    b = [int(r["rater_b"]) for r in rows]
    by_need: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_need[r["pair_id"].split("-")[0]].append(r)
    ndcgs, top_hits = [], []
    for items in by_need.values():
        items.sort(key=lambda r: int(r["_rank"]))  # порядок нашего подбора
        expert = [(int(r["rater_a"]) + int(r["rater_b"])) / 2 for r in items]
        ndcgs.append(_ndcg(expert))
        top_hits.append(expert[0] == max(expert))
    mean_expert = [(x + y) / 2 for x, y in zip(a, b, strict=True)]
    truth = [int(r["_truth"]) for r in rows]
    agree_truth = statistics.fmean(
        abs(e - t) <= 1 for e, t in zip(mean_expert, truth, strict=True)
    )
    REPORT.write_text(
        f"""# Валидация подбора по экспертной разметке

Сгенерировано `uv run python -m validation.expert report` (из `scoring/`) по
`docs/expert/pairs.csv`: {len(rows)} пар, {len(by_need)} потребностей, двое разметчиков независимо,
шкала 0-3. Пары из слепого генератора: 3 кандидата из топа подбора и 2 случайных на потребность,
перемешаны, скор системы разметчики не видели.

| Метрика | Значение |
|---|---|
| Согласие разметчиков, взвешенная каппа Коэна | {weighted_kappa(a, b):.2f} |
| Точное совпадение оценок | {statistics.fmean(x == y for x, y in zip(a, b, strict=True)):.0%} |
| nDCG@5 порядка подбора против средней экспертной оценки | {statistics.fmean(ndcgs):.2f} |
| Первый кандидат подбора: среди лучших по мнению экспертов | {statistics.fmean(top_hits):.0%} |
| Эксперты и скрытая релевантность генератора расходятся не больше чем на 1 балл | {agree_truth:.0%} |

Каппа выше 0.6 означает существенное согласие, и разметка годится как эталон. Последняя строка проверяет
сам генератор: если эксперты с ним не согласны, его «истинная» релевантность плохой эталон для
остальных отчётов.
""",
        encoding="utf-8",
    )
    print(REPORT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    {"sample": sample, "report": report}[
        sys.argv[1] if len(sys.argv) > 1 else "sample"
    ]()
