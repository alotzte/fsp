import os
import shutil
import subprocess
from collections import Counter
from random import Random

import pytest

from app.services.assessment.assembly import (
    BLUEPRINTS,
    EXPRESS_EXTENSION_ITEMS,
    EXTENSION_ITEMS,
    EXTENSION_ROUNDS,
    ScoredResponse,
    assemble,
    extend,
    extension_size,
    is_correct,
    matches_foreign,
    score_attempt,
    select_families,
    shortened,
    weekly_case,
)
from app.services.assessment.bank import FAMILIES, ItemKind, normalize_answer
from app.services.assessment.irt import (
    CONFIDENCE_K,
    GRADE_THRESHOLDS,
    AbilityEstimate,
    ItemResponse,
    decide_grade,
    estimate_ability,
    retest_agreement,
)

SEEDS = range(40)


@pytest.mark.parametrize("family_id", sorted(FAMILIES))
def test_family_instances_are_valid_and_deterministic(family_id: str) -> None:
    family = FAMILIES[family_id]
    prompts = set()
    for seed in SEEDS:
        item = family.generate(Random(seed))
        assert item == family.generate(Random(seed)), (
            "экземпляр должен зависеть только от seed"
        )
        assert item.prompt and item.answer
        if item.kind == ItemKind.CHOICE:
            normalized = [normalize_answer(o) for o in item.options]
            assert len(item.options) >= 3
            assert len(set(normalized)) == len(normalized), (
                "варианты не должны повторяться"
            )
            assert normalize_answer(item.answer) in normalized
        else:
            assert not item.options
        prompts.add((item.prompt, item.code, tuple(item.options)))
    # Семейство должно давать разные экземпляры, иначе оно не защищает от утечки.
    assert len(prompts) > 1


@pytest.mark.parametrize("family_id", sorted(FAMILIES))
def test_leaked_answer_rarely_fits_another_instance(family_id: str) -> None:
    """Утечка экземпляра не должна давать ответ на чужой экземпляр того же семейства."""
    answers = Counter(
        normalize_answer(FAMILIES[family_id].generate(Random(seed)).answer)
        for seed in range(200)
    )
    collision = sum(c * (c - 1) for c in answers.values()) / (200 * 199)
    assert collision < 0.5


@pytest.mark.skipif(shutil.which("node") is None, reason="нужен Node.js")
@pytest.mark.parametrize(
    "family_id", sorted(f for f in FAMILIES if f.startswith("js."))
)
def test_js_answers_match_real_engine(family_id: str) -> None:
    """Ответы JS-семейств считаются моделью семантики на Python: сверяем с настоящим V8."""
    # FORCE_COLOR в окружении раскрашивает console.log даже в pipe: сравнивали бы ANSI-коды.
    env = {k: v for k, v in os.environ.items() if k != "FORCE_COLOR"} | {
        "NO_COLOR": "1"
    }
    for seed in range(15):
        item = FAMILIES[family_id].generate(Random(seed))
        assert item.code is not None
        run = subprocess.run(
            ["node", "--input-type=module", "-e", item.code],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=env,
        )
        output = "TypeError" if "TypeError" in run.stderr else run.stdout
        assert normalize_answer(output) == normalize_answer(item.answer), item.code


def test_normalize_answer() -> None:
    assert normalize_answer(" 0,42 ") == "0.42"
    assert normalize_answer("3, 3, 3") == "3 3 3"
    assert is_correct("True False", "true  false")
    assert not is_correct("1", None)


def test_estimate_grows_with_correct_answers() -> None:
    items = [(1.3, b) for b in (-1.0, -0.5, 0.0, 0.5, 1.0, 1.5)]
    thetas = [
        estimate_ability(
            [ItemResponse(a, b, i < k) for i, (a, b) in enumerate(items)]
        ).theta
        for k in range(len(items) + 1)
    ]
    assert thetas == sorted(thetas)
    assert thetas[0] < -1 < 1 < thetas[-1]


def test_grade_decision() -> None:
    middle = GRADE_THRESHOLDS[2]
    assert decide_grade(AbilityEstimate(middle + 0.5, 0.3), 2).passed
    assert not decide_grade(
        AbilityEstimate(middle + 0.05, 0.4), 2
    ).passed  # запас на погрешность
    weak = decide_grade(AbilityEstimate(-0.5, 0.3), 2)
    assert not weak.passed and weak.estimated_level == 1
    assert decide_grade(AbilityEstimate(1.6, 0.3), 2).strong
    assert decide_grade(
        AbilityEstimate(-3.0, 0.5), 0
    ).passed  # стажёр подтверждается всегда


@pytest.mark.parametrize("slug", sorted(BLUEPRINTS))
@pytest.mark.parametrize("level", range(5))
def test_assembly_follows_blueprint(slug: str, level: int) -> None:
    blueprint = BLUEPRINTS[slug]
    items = assemble(blueprint, level, seed=7)
    assert [i.item for i in items] == [
        i.item for i in assemble(blueprint, level, seed=7)
    ]
    assert len(items) == blueprint.items_count
    assert len({i.family.id for i in items}) == len(items)
    for competency, count in blueprint.quotas.items():
        assert sum(i.family.competency == competency for i in items) == count


def test_recent_families_are_avoided() -> None:
    blueprint = BLUEPRINTS["backend"]
    first = {f.id for f in select_families(blueprint, 2, Random(1))}
    second = {
        f.id for f in select_families(blueprint, 2, Random(2), recent_families=first)
    }
    # Повтор возможен только там, где в компетенции не хватает свежих семейств.
    for competency, count in blueprint.quotas.items():
        fresh = sum(
            f.competency == competency and f.id not in first for f in FAMILIES.values()
        )
        repeated = sum(FAMILIES[f].competency == competency for f in first & second)
        assert repeated == max(0, count - fresh)


def test_score_attempt_checks_answers() -> None:
    items = assemble(BLUEPRINTS["backend"], 2, seed=3)
    perfect = [
        ScoredResponse(i.family.a, i.family.b, i.item.answer, i.item.answer)
        for i in items
    ]
    empty = [ScoredResponse(i.family.a, i.family.b, i.item.answer, None) for i in items]
    assert all(score_attempt(2, perfect).correct)
    assert score_attempt(2, perfect).decision.passed
    assert not score_attempt(2, empty).decision.passed


def test_retest_agreement_is_a_coin_at_the_boundary() -> None:
    senior = GRADE_THRESHOLDS[3]
    se = 0.4
    boundary = AbilityEstimate(senior + CONFIDENCE_K * se, se)
    assert retest_agreement(boundary, 3) == pytest.approx(0.5)
    sure_pass = AbilityEstimate(senior + 3 * se, se)
    sure_fail = AbilityEstimate(senior - 3 * se, se)
    assert decide_grade(sure_pass, 3).passed
    assert not decide_grade(sure_fail, 3).passed
    assert retest_agreement(sure_pass, 3) > 0.95
    assert retest_agreement(sure_fail, 3) > 0.95
    # Чем ближе к порогу, тем менее устойчиво решение.
    near = AbilityEstimate(senior + 1.0 * se, se)
    assert 0.5 < retest_agreement(near, 3) < retest_agreement(sure_pass, 3)
    assert retest_agreement(AbilityEstimate(-3.0, 0.5), 0) == 1.0


def test_near_threshold() -> None:
    middle = GRADE_THRESHOLDS[2]
    assert decide_grade(AbilityEstimate(middle + 0.2, 0.4), 2).near_threshold
    assert decide_grade(AbilityEstimate(middle - 0.3, 0.4), 2).near_threshold
    assert not decide_grade(AbilityEstimate(middle + 0.9, 0.4), 2).near_threshold
    assert not decide_grade(AbilityEstimate(-1.5, 0.4), 0).near_threshold


@pytest.mark.parametrize("slug", sorted(BLUEPRINTS))
@pytest.mark.parametrize("level", range(1, 5))
def test_extension_targets_threshold_without_repeats(slug: str, level: int) -> None:
    blueprint = BLUEPRINTS[slug]
    shown = {i.family.id for i in assemble(blueprint, level, seed=3)}
    extra = extend(blueprint, level, seed=3, count=5, attempt_families=shown)
    assert len(extra) == 5
    assert not shown & {i.family.id for i in extra}
    assert all(i.family.competency in blueprint.quotas for i in extra)
    # Взяты ближайшие к порогу из оставшихся.
    threshold = GRADE_THRESHOLDS[level]
    taken = {i.family.id for i in extra}
    rest = [
        f
        for f in FAMILIES.values()
        if f.competency in blueprint.quotas and f.id not in shown | taken
    ]
    farthest_taken = max(abs(i.family.b - threshold) for i in extra)
    assert all(abs(f.b - threshold) >= farthest_taken for f in rest)
    assert [i.item for i in extra] == [
        i.item
        for i in extend(blueprint, level, seed=3, count=5, attempt_families=shown)
    ]


def test_uncertain_decision_extends_attempt_limited_times() -> None:
    assert (
        extension_size(near_threshold=True, extensions=0, express=False)
        == EXTENSION_ITEMS
    )
    last_round = EXTENSION_ROUNDS - 1
    assert (
        extension_size(near_threshold=True, extensions=last_round, express=False)
        == EXTENSION_ITEMS
    )
    assert (
        extension_size(near_threshold=True, extensions=EXTENSION_ROUNDS, express=False)
        == 0
    )
    assert extension_size(near_threshold=False, extensions=0, express=False) == 0
    assert (
        extension_size(near_threshold=True, extensions=0, express=True)
        == EXPRESS_EXTENSION_ITEMS
    )


def test_extension_prefers_fresh_families() -> None:
    blueprint = BLUEPRINTS["backend"]
    nearest = extend(blueprint, 4, seed=1, count=3, attempt_families=set())
    recent = {i.family.id for i in nearest}
    fresh = extend(
        blueprint, 4, seed=1, count=3, attempt_families=set(), recent_families=recent
    )
    assert not recent & {i.family.id for i in fresh}


@pytest.mark.parametrize("slug", sorted(BLUEPRINTS))
def test_weekly_case_is_deterministic_and_on_specialization(slug: str) -> None:
    blueprint = BLUEPRINTS[slug]
    cases = [weekly_case(blueprint, 2, seed) for seed in range(30)]
    assert all(c.family.competency in blueprint.quotas for c in cases)
    assert [c.item for c in cases] == [
        weekly_case(blueprint, 2, s).item for s in range(30)
    ]
    # Разные недели дают разные задания: кейс не повторяется по кругу.
    assert len({c.family.id for c in cases}) > 3


def test_http_api_roundtrip() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    assert {
        b["specialization"] for b in client.get("/assessment/blueprints").json()
    } == set(BLUEPRINTS)
    assert (
        client.post(
            "/assessment/assemble",
            json={"specialization": "gamedev", "level": 1, "seed": 1},
        ).status_code
        == 404
    )
    items = client.post(
        "/assessment/assemble",
        json={"specialization": "frontend", "level": 3, "seed": 5},
    ).json()
    scored = client.post(
        "/assessment/score",
        json={
            "level": 3,
            "items": [
                {
                    "a": i["a"],
                    "b": i["b"],
                    "answer": i["answer"],
                    "response": i["answer"],
                }
                for i in items
            ],
        },
    ).json()
    assert scored["passed"] and all(scored["correct"])
    assert scored["extend_items"] == 0 and scored["retest_agreement"] > 0.5
    extra = client.post(
        "/assessment/extend",
        json={
            "specialization": "frontend",
            "level": 3,
            "seed": 5,
            "count": 5,
            "attempt_families": [i["family_id"] for i in items],
        },
    ).json()
    assert len(extra) == 5
    assert not {i["family_id"] for i in items} & {i["family_id"] for i in extra}
    case = client.post(
        "/assessment/case", json={"specialization": "backend", "level": 2, "seed": 9}
    ).json()
    assert case["answer"] and case["family_id"]


@pytest.mark.parametrize("slug", sorted(BLUEPRINTS))
def test_express_test_keeps_every_competency(slug: str) -> None:
    blueprint = BLUEPRINTS[slug]
    express = shortened(blueprint, 6)
    assert express.items_count == 6
    assert set(express.quotas) == set(blueprint.quotas)
    assert all(n >= 1 for n in express.quotas.values())
    assert express.time_limit_minutes == 6
    assert len(assemble(express, 2, seed=1)) == 6


def test_foreign_answer_is_flagged_as_leak() -> None:
    assert (
        matches_foreign("42", "42 ", ["17", "42"]) is False
    )  # свой эталон: просто верно
    assert matches_foreign("42", "17", ["17"]) is True  # чужой эталон: утечка
    assert matches_foreign("42", "5", ["17"]) is False  # просто ошибка
    assert matches_foreign("42", None, ["17"]) is False
    responses = [ScoredResponse(1.0, 0.0, "42", "17", ("17",))]
    assert score_attempt(1, responses).foreign_matches == [True]
