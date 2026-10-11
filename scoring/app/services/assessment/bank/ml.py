"""Компетенции «Машинное обучение» и «Статистика». Численные ответы вычисляются."""

import math
import statistics
from fractions import Fraction
from random import Random

from app.services.assessment.bank.base import Item, choice, family, text

ML = "ml"
STATS = "stats"


@family("ml.fit_diagnosis", competency=ML, a=1.1, b=-1.0)
def _fit_diagnosis(rng: Random) -> Item:
    overfit = (
        "Переобучение: усилить регуляризацию, упростить модель или добавить данных"
    )
    underfit = "Недообучение: усложнить модель или добавить признаки"
    suspicious = "Подозрительно: валидация не должна быть заметно лучше обучения, проверить разбиение"
    train, val, correct = rng.choice(
        [
            (rng.randint(96, 99), rng.randint(65, 78), overfit),
            (rng.randint(58, 66), rng.randint(55, 63), underfit),
            (rng.randint(72, 80), rng.randint(91, 97), suspicious),
        ]
    )
    return choice(
        rng,
        f"Accuracy на обучении {train}%, на валидации {val}%. Какой диагноз и что делать?",
        correct,
        [overfit, underfit, suspicious, "Всё в порядке: такая разница метрик ожидаема"],
    )


@family("ml.precision_recall", competency=ML, a=1.3, b=-0.3)
def _precision_recall(rng: Random) -> Item:
    tp, fp, fn, tn = (rng.randint(5, 60) for _ in range(4))
    metric = rng.choice(["precision", "recall"])
    denominator = tp + fp if metric == "precision" else tp + fn
    # Округление «как в школе» (0.625 → 0.63) в целых числах: f"{x:.2f}" округлял половины
    # к чётному и по двоичной записи (0.625 → 0.62, 0.825 → 0.82).
    hundredths = (200 * tp + denominator) // (2 * denominator)
    code = f"TP = {tp}, FP = {fp}\nFN = {fn}, TN = {tn}"
    return text(
        f"По матрице ошибок посчитайте {metric}. Ответ округлите до двух знаков (например, 0.42).",
        f"{hundredths / 100:.2f}",
        code,
    )


@family("ml.imbalance", competency=ML, a=1.3, b=0.3)
def _imbalance(rng: Random) -> Item:
    situation, correct = rng.choice(
        [
            (
                (
                    f"Доля мошеннических транзакций: {rng.choice([1, 2])}%. Модель, всегда "
                    "отвечающая «не мошенничество», даёт высокую accuracy. Какая метрика сразу "
                    "покажет, что модель бесполезна?"
                ),
                "Recall",
            ),
            (
                (
                    "Спам-фильтр: ошибочно спрятать важное письмо намного хуже, чем пропустить спам. "
                    "Какую метрику класса «спам» важнее держать высокой?"
                ),
                "Precision",
            ),
            (
                (
                    "Скрининг редкого заболевания: пропустить больного намного хуже, чем отправить "
                    "здорового на дообследование. Какую метрику важнее держать высокой?"
                ),
                "Recall",
            ),
            (
                (
                    f"Дефектных деталей {rng.choice([1, 3, 5])}%. Какая метрика здесь вводит в "
                    "заблуждение сильнее всего?"
                ),
                "Accuracy",
            ),
        ]
    )
    return choice(
        rng, situation, correct, ["Accuracy", "Precision", "Recall", "Specificity"]
    )


_PIPELINES_OK = [
    "Делят на train/test, затем StandardScaler обучают (fit) только на train",
    "Пропуски заполняют средним, посчитанным только по train",
    "Признаки клиента считают только по покупкам до даты прогноза",
]
_PIPELINES_LEAK = [
    "StandardScaler обучают (fit) на всём датасете, затем делят на train/test",
    "Пропуски заполняют средним по всему датасету, затем делят на train/test",
    "Признак «средний чек клиента» считают по всем покупкам, включая тестовый период",
    "Target encoding категорий считают по всему датасету до разбиения",
]


@family("ml.leakage", competency=ML, a=1.4, b=0.6)
def _leakage(rng: Random) -> Item:
    if rng.random() < 0.5:
        return choice(
            rng,
            "В каком из пайплайнов есть утечка данных, завышающая метрику на тесте?",
            rng.choice(_PIPELINES_LEAK),
            _PIPELINES_OK,
        )
    return choice(
        rng,
        "Какой из пайплайнов свободен от утечки данных?",
        rng.choice(_PIPELINES_OK),
        rng.sample(_PIPELINES_LEAK, 3),
    )


_CV_STRATEGIES = {
    "TimeSeriesSplit: обучение на прошлом, проверка на следующем периоде": (
        "Модель прогнозирует {target} на следующий период."
    ),
    "GroupKFold по пользователю: все строки одного человека в одном фолде": (
        "В датасете по 20-50 сессий на каждого пользователя, модель будет применяться к новым "
        "пользователям."
    ),
    "StratifiedKFold: доли классов в фолдах как во всей выборке": (
        "Бинарная классификация, положительный класс: 3% строк, наблюдения независимы."
    ),
}


@family("ml.cv_strategy", competency=ML, a=1.4, b=1.2)
def _cv_strategy(rng: Random) -> Item:
    correct = rng.choice(list(_CV_STRATEGIES))
    target = rng.choice(
        ["спрос по дням", "нагрузку на сервис по часам", "выручку по неделям"]
    )
    return choice(
        rng,
        f"{_CV_STRATEGIES[correct].format(target=target)} Какую схему кросс-валидации выбрать?",
        correct,
        [*[s for s in _CV_STRATEGIES if s != correct], "KFold с перемешиванием строк"],
    )


@family("ml.regularization", competency=ML, a=1.4, b=1.9)
def _regularization(rng: Random) -> Item:
    goal, correct = rng.choice(
        [
            ("получить разреженную модель и отобрать признаки", "L1 (Lasso)"),
            (
                "оставить все сильно коррелированные признаки, равномерно сжав их веса",
                "L2 (Ridge)",
            ),
            (
                "отобрать признаки, но не выбрасывать случайно один из группы коррелированных",
                "Elastic Net (L1 + L2)",
            ),
        ]
    )
    return choice(
        rng,
        f"Линейная модель, 500 признаков. Нужно {goal}. Какую регуляризацию выбрать?",
        correct,
        ["L1 (Lasso)", "L2 (Ridge)", "Elastic Net (L1 + L2)", "Dropout"],
    )


@family("stats.median", competency=STATS, a=1.1, b=-1.2)
def _median(rng: Random) -> Item:
    values = [rng.randint(1, 40) for _ in range(rng.choice([5, 6, 7, 8]))]
    median = statistics.median(values)
    answer = int(median) if median == int(median) else f"{median:.1f}"
    return text(
        f"Найдите медиану: {', '.join(map(str, values))}. Дробную часть, если есть, "
        "запишите через точку.",
        answer,
    )


@family("stats.dice", competency=STATS, a=1.2, b=-0.4)
def _dice(rng: Random) -> Item:
    target = rng.randint(3, 11)
    relation, check = rng.choice([("равна", target.__eq__), ("больше", target.__lt__)])
    favorable = sum(1 for a in range(1, 7) for b in range(1, 7) if check(a + b))
    return text(
        f"Бросают два честных кубика. Сколько из 36 равновозможных исходов дают сумму, "
        f"которая {relation} {target}?",
        favorable,
    )


@family("stats.std_transform", competency=STATS, a=1.3, b=0.0)
def _std_transform(rng: Random) -> Item:
    sigma = rng.randint(2, 9)
    k = rng.choice([2, 3, -2, 10])
    c = rng.randint(-50, 100)
    return text(
        f"Стандартное отклонение выборки равно {sigma}. Каждое значение заменили на "
        f"{k}·x + {c}. Каким стало стандартное отклонение?",
        abs(k) * sigma,
    )


@family("stats.pvalue", competency=STATS, a=1.3, b=0.5)
def _pvalue(rng: Random) -> Item:
    alpha = rng.choice([0.05, 0.01])
    p = rng.choice([0.003, 0.02, 0.04, 0.12])
    reject = "Отвергаем H0 на уровне значимости α"
    keep = "Нет оснований отвергнуть H0 на уровне значимости α"
    meaning = "Вероятность получить такие или более экстремальные данные, если H0 верна"
    wrong = [
        f"Вероятность того, что H0 верна, равна {p}",
        "Вероятность, что эффект случаен",
    ]
    if rng.random() < 1 / 3:
        return choice(
            rng,
            f"A/B-тест дал p-value = {p}. Что это означает?",
            meaning,
            [*wrong, reject],
        )
    return choice(
        rng,
        f"A/B-тест: α = {alpha}, p-value = {p}. Какой вывод корректен?",
        reject if p < alpha else keep,
        [reject, keep, *wrong],
    )


@family("stats.sample_size", competency=STATS, a=1.4, b=1.0)
def _sample_size(rng: Random) -> Item:
    factor = rng.choice([2, 3, 4])
    return text(
        f"Во сколько раз нужно увеличить размер выборки, чтобы стандартная ошибка среднего "
        f"уменьшилась в {factor} раза?",
        factor * factor,
    )


@family("stats.bayes", competency=STATS, a=1.5, b=2.0)
def _bayes(rng: Random) -> Item:
    prevalence = Fraction(rng.choice([1, 2, 5]), 100)
    sensitivity = Fraction(rng.choice([90, 95, 99]), 100)
    specificity = Fraction(rng.choice([90, 95, 98]), 100)
    positive = sensitivity * prevalence + (1 - specificity) * (1 - prevalence)
    posterior = sensitivity * prevalence / positive
    return text(
        f"Болезнью страдает {prevalence * 100}% людей. Тест находит болезнь у "
        f"{sensitivity * 100}% больных и даёт ложную тревогу у {(1 - specificity) * 100}% "
        "здоровых. Человек получил положительный результат. Какова вероятность, что он болен? "
        "Ответ: в процентах, округлите до целого.",
        round(float(posterior) * 100),
    )


def _percent(share: Fraction) -> int:
    """Доля в процентах с округлением «половина вверх», как считают люди (round() в Python
    округлил бы 62.5 до 62)."""
    return math.floor(share * 100 + Fraction(1, 2))


@family("ml.roc_auc", competency=ML, a=1.4, b=1.9)
def _roc_auc(rng: Random) -> Item:
    while True:
        n = rng.randint(7, 9)
        scores = rng.sample(range(5, 100, 5), n)
        labels = [rng.random() < 0.5 for _ in range(n)]
        positive = [s for s, y in zip(scores, labels, strict=True) if y]
        negative = [s for s, y in zip(scores, labels, strict=True) if not y]
        if len(positive) < 2 or len(negative) < 2:
            continue
        # AUC: доля пар (класс 1, класс 0), где у класса 1 оценка выше.
        ordered = sum(p > q for p in positive for q in negative)
        auc = Fraction(ordered, len(positive) * len(negative))
        if 0 < auc < 1:
            break
    rows = "\n".join(
        f"{i} | 0.{s:02d} | {int(y)}"
        for i, (s, y) in enumerate(zip(scores, labels, strict=True), 1)
    )
    return text(
        "Модель выдала оценки вероятности класса 1 (ниже). Чему равен ROC AUC на этих "
        "данных? Ответ: в процентах, округлите до целого (например, 0.83 → 83).",
        _percent(auc),
        code=f"объект | оценка | класс\n{rows}",
    )


def _cost(
    scores: list[int], labels: list[bool], threshold: int, fp: int, fn: int
) -> int:
    false_alarms = sum(
        s >= threshold and not y for s, y in zip(scores, labels, strict=True)
    )
    misses = sum(s < threshold and y for s, y in zip(scores, labels, strict=True))
    return fp * false_alarms + fn * misses


@family("ml.cost_threshold", competency=ML, a=1.5, b=2.3)
def _cost_threshold(rng: Random) -> Item:
    while True:
        scores = sorted(rng.sample(range(5, 100, 10), 8))
        labels = [rng.random() < s / 100 for s in scores]
        fp, fn = rng.choice([(1, 5), (1, 4), (1, 3), (3, 1), (4, 1), (5, 1)])
        costs = {t: _cost(scores, labels, t, fp, fn) for t in scores}
        errors = {t: _cost(scores, labels, t, 1, 1) for t in scores}
        best = [t for t in scores if costs[t] == min(costs.values())]
        fewest_errors = [t for t in scores if errors[t] == min(errors.values())]
        # Порог по стоимости единственный и отличается от порога с наименьшим числом ошибок:
        # без учёта цены ошибок ответ не получить.
        if len(best) == 1 and best[0] not in fewest_errors:
            break
    rows = "\n".join(
        f"0.{s:02d} | {int(y)}" for s, y in zip(scores, labels, strict=True)
    )
    return text(
        f"Объект относят к классу 1, если оценка модели ≥ порога. Ложная тревога (предсказали 1, "
        f"на деле 0) стоит {fp}, пропуск (предсказали 0, на деле 1): {fn}. Какой порог из "
        "оценок ниже даёт наименьшую суммарную стоимость ошибок на этих данных?",
        f"0.{best[0]:02d}",
        code=f"оценка | класс\n{rows}",
    )


@family("stats.simpson", competency=STATS, a=1.4, b=1.9)
def _simpson(rng: Random) -> Item:
    while True:
        segments = [
            (variant, segment, visits, visits * rng.randint(2, 30) // 100)
            for variant in ("A", "B")
            for segment in ("мобильные", "десктоп")
            for visits in [rng.randrange(200, 2001, 100)]
        ]
        target = rng.choice(["A", "B"])
        mine = [(v, c) for variant, _, v, c in segments if variant == target]
        overall = Fraction(sum(c for _, c in mine), sum(v for v, _ in mine))
        naive = sum((Fraction(c, v) for v, c in mine), Fraction(0)) / 2
        # Среднее конверсий сегментов даёт другой ответ: проверяем взвешивание по трафику.
        if _percent(overall) != _percent(naive):
            break
    rows = "\n".join(
        f"{variant} | {segment} | {v} | {c}" for variant, segment, v, c in segments
    )
    return text(
        f"Результаты A/B-теста по сегментам ниже. Какова общая конверсия варианта {target} "
        "(доля визитов с конверсией по всем сегментам)? Ответ: в процентах, округлите до целого.",
        _percent(overall),
        code=f"вариант | сегмент | визиты | конверсии\n{rows}",
    )


_PVALUES = [
    "0.001",
    "0.004",
    "0.008",
    "0.011",
    "0.014",
    "0.019",
    "0.024",
    "0.031",
    "0.044",
    "0.062",
    "0.12",
    "0.27",
]
_CORRECTIONS = ["Бонферрони", "Холма", "Бенджамини-Хохберга"]


def rejected_hypotheses(
    pvalues: list[Fraction], method: str, alpha: Fraction
) -> list[int]:
    """Номера (с 1) отвергнутых гипотез при поправке на множественные сравнения."""
    m = len(pvalues)
    ranked = sorted(range(m), key=lambda i: pvalues[i])
    if method == "Бонферрони":
        return [i + 1 for i in range(m) if pvalues[i] <= alpha / m]
    if method == "Холма":
        rejected = []
        for k, i in enumerate(ranked):
            if pvalues[i] > alpha / (m - k):
                break
            rejected.append(i + 1)
        return sorted(rejected)
    # Бенджамини-Хохберг: наибольший ранг k с p(k) ≤ k·α/m, отвергаются все до него.
    last = max(
        (k for k, i in enumerate(ranked, 1) if pvalues[i] <= k * alpha / m), default=0
    )
    return sorted(i + 1 for i in ranked[:last])


@family("stats.multiple_testing", competency=STATS, a=1.5, b=2.3)
def _multiple_testing(rng: Random) -> Item:
    alpha = Fraction(1, 20)
    while True:
        raw = rng.sample(_PVALUES, rng.randint(4, 6))
        pvalues = [Fraction(p) for p in raw]
        method = rng.choice(_CORRECTIONS)
        results = {m: rejected_hypotheses(pvalues, m, alpha) for m in _CORRECTIONS}
        # Поправки расходятся на этих данных: ответ требует знать именно эту процедуру.
        if sum(r == results[method] for r in results.values()) == 1:
            break
    labels = " ".join(f"H{i}" for i in results[method])
    return text(
        f"Одновременно проверили гипотезы H1-H{len(raw)}, уровень значимости α = 0.05 на всё "
        f"семейство. Какие гипотезы отвергнет поправка {method}? Перечислите через пробел "
        "(например, H1 H3); если ни одной: напишите «нет».",
        labels or "нет",
        code="\n".join(f"H{i}: p = {p}" for i, p in enumerate(raw, 1)),
    )
