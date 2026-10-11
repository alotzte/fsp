"""Эксперимент 5.4: эмбеддинги для навыков вне словаря на слепом генераторе.

Запуск (из scoring/, тяжёлые зависимости только на время запуска, в проект не добавляются):

    PYTHONPATH=. uv run --with sentence-transformers --with numpy --with torch \\
      --index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match \\
      python validation/embeddings.py

Модель cointegrated/rubert-tiny2 (MIT, CPU). Перефраз навыка вне словаря («питон», «датафреймы»)
сопоставляется ближайшему названию или синониму словаря по косинусной близости; найденный навык
добавляется кандидату, и подбор пересчитывается. Итоги: docs/architecture.md §8.
"""

import statistics
from dataclasses import replace

import numpy as np
from sentence_transformers import SentenceTransformer

from validation import matching as m

model = SentenceTransformer("cointegrated/rubert-tiny2", device="cpu")
names = [(sid, n) for sid, (t, al, _) in m.VOCAB.items() for n in (t, *al)]
vecs = model.encode([n for _, n in names], normalize_embeddings=True)
para = {p for _, (_, _, ps) in m.VOCAB.items() for p in ps}
pv = dict(zip(sorted(para), model.encode(sorted(para), normalize_embeddings=True)))


def nearest(mention):
    sims = vecs @ pv[mention]
    i = int(np.argmax(sims))
    return names[i][0], float(sims[i])


truth = {p: sid for sid, (_, _, ps) in m.VOCAB.items() for p in ps}
for th in (0.5, 0.6, 0.7, 0.8):
    hits = [(nearest(p), truth[p]) for p in para]
    resolved = [(s, t) for (s, sim), t in hits if sim >= th]
    correct = sum(s == t for s, t in resolved)
    print(
        f"порог {th}: распознано {len(resolved)}/{len(para)} перефразов, верно {correct}"
    )


def run(th):
    cases = m.build_cases(2027, 0.25, blind=True)
    out = []
    for need, pool in cases:
        new_pool = []
        for c in pool:
            mentions = c.resume.split("Навыки: ", 1)[1].split(", ")
            extra = {nearest(x)[0] for x in mentions if x in pv and nearest(x)[1] >= th}
            new_pool.append(
                replace(
                    c,
                    features=replace(
                        c.features, skills=c.features.skills | frozenset(extra)
                    ),
                )
            )
        rel = {c.features.key: m.relevance(need, c) for c in new_pool}
        out.append(m.ndcg(m.ours(need, new_pool), rel))
    return statistics.fmean(out)


base = m.evaluate(m.ours, m.build_cases(2027, 0.25, blind=True)).ndcg10
print("nDCG@10 без эмбеддингов", round(base, 3))
for th in (0.6, 0.7, 0.8):
    print("с эмбеддингами, порог", th, round(run(th), 3))
