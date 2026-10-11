from app.services.matching import (
    CandidateFeatures,
    Need,
    NeedSkill,
    level_posterior,
    match_candidate,
    profile_strength,
    rank,
)

PY, SQL, KAFKA = 1, 2, 3
NEED = Need(
    grade_level=2,
    skills=[
        NeedSkill(PY, "Python", True),
        NeedSkill(SQL, "SQL", True),
        NeedSkill(KAFKA, "Kafka", False),
    ],
    work_formats=frozenset({"remote"}),
    salary_to=300_000,
)


def candidate(key: int, **fields: object) -> CandidateFeatures:
    base: dict[str, object] = {
        "grade_level": 2,
        "grade_title": "Middle",
        "confirmed": True,
        "theta": 0.6,
        "theta_se": 0.4,
        "skills": frozenset({PY, SQL}),
        "work_formats": frozenset({"remote"}),
    }
    return CandidateFeatures(key=key, **(base | fields))  # type: ignore[arg-type]


def test_strength_orders_confirmed_above_unconfirmed() -> None:
    assert profile_strength(candidate(1, confirmed=False)) == 0
    assert (
        0.5
        <= profile_strength(candidate(1, theta=0.1))
        < profile_strength(candidate(1, theta=1.5))
    )


def test_ranking_follows_need() -> None:
    ranked = rank(
        NEED,
        [
            candidate(1, skills=frozenset({PY})),  # нет обязательного SQL
            candidate(2),  # всё обязательное
            candidate(3, skills=frozenset({PY, SQL, KAFKA})),  # плюс желательное
            candidate(4, confirmed=False),  # грейд не подтверждён
            candidate(5, grade_level=3, grade_title="Senior"),  # соседний грейд
        ],
    )
    assert [m.key for m in ranked][:2] == [3, 2]
    assert ranked[-1].key in {1, 4, 5}
    first = ranked[0]
    assert "Есть все обязательные навыки" in first.reasons
    assert (
        abs(first.score - sum(c.value * c.weight for c in first.contributions)) < 1e-9
    )
    weak = next(m for m in ranked if m.key == 1)
    assert any("нет SQL" in r for r in weak.reasons)


def test_salary_threshold_is_hidden_but_respected() -> None:
    ranked = rank(
        NEED, [candidate(1, salary_expectation=400_000), candidate(2, theta=0.0)]
    )
    assert [m.key for m in ranked] == [2, 1]
    assert not ranked[1].salary_compatible
    assert all("400" not in r for r in ranked[1].reasons)


def test_bank_search_without_need_ranks_by_profile() -> None:
    ranked = rank(
        None,
        [
            candidate(1, confirmed=False),
            candidate(2, fsp_score=0.9, fsp_achievements=2),
            candidate(3),
        ],
    )
    assert [m.key for m in ranked] == [2, 3, 1]
    assert any("Достижения ФСП: 2" in r for r in ranked[0].reasons)


def test_relevant_fsp_discipline_is_explained_without_changing_score() -> None:
    plain = candidate(1, fsp_score=0.6, fsp_achievements=2)
    relevant = candidate(2, fsp_score=0.6, fsp_achievements=2, fsp_relevant=1)
    a, b = (match_candidate(NEED, c) for c in (plain, relevant))
    assert a.score == b.score
    assert any("по профильной дисциплине: 1" in r for r in b.reasons)
    assert all("профильной" not in r for r in a.reasons)


def test_no_fsp_history_is_not_penalised() -> None:
    """Обязательный случай ТЗ: без истории ФСП кандидат теряет только бонус, без штрафа."""
    ranked = rank(NEED, [candidate(1), candidate(2, fsp_score=0.6, fsp_achievements=1)])
    without = next(m for m in ranked if m.key == 1)
    assert without.score > 0.5
    assert all("ФСП" not in r for r in without.reasons)


def test_format_mismatch_goes_below_but_not_blocked() -> None:
    ranked = rank(
        NEED,
        [candidate(1, work_formats=frozenset({"office"})), candidate(2, theta=0.0)],
    )
    assert [m.key for m in ranked] == [2, 1]
    assert not ranked[1].format_compatible and ranked[1].salary_compatible


def test_test_result_updates_claimed_grade() -> None:
    claimed_only = level_posterior(
        candidate(1, confirmed=False, theta=None, theta_se=None)
    )
    assert claimed_only[2] > 0.5
    # Провалил тест на Middle с оценкой уровня Junior: вероятнее Junior.
    failed = level_posterior(candidate(1, confirmed=False, theta=-0.6, theta_se=0.35))
    assert failed[1] > failed[2]
    confirmed = level_posterior(candidate(1, theta=0.5, theta_se=0.35))
    assert confirmed[2] > claimed_only[2]
    assert abs(sum(confirmed.values()) - 1) < 1e-9


def test_verified_skills_are_explained_but_do_not_change_score() -> None:
    plain = rank(NEED, [candidate(1)])[0]
    checked = rank(NEED, [candidate(1, verified_skills=frozenset({PY}))])[0]
    assert checked.score == plain.score
    assert [(s.title, s.status) for s in checked.skills] == [
        ("Python", "verified"),
        ("SQL", "claimed"),
        ("Kafka", "missing"),
    ]
    assert "Подтверждено тестом 1 из 3 навыков потребности: Python" in checked.reasons
    assert not any("Подтверждено тестом" in r for r in plain.reasons)


def test_weekly_cases_are_explained_but_do_not_change_score() -> None:
    plain = rank(NEED, [candidate(1)])[0]
    active = rank(NEED, [candidate(1, recent_cases=3)])[0]
    assert active.score == plain.score
    assert "Решает кейсы недели: 3 за 30 дней" in active.reasons
    assert not any("кейсы недели" in r for r in plain.reasons)


def test_city_spelling_and_empty_fields_are_not_mismatches() -> None:
    office = Need(
        grade_level=2, skills=[], work_formats=frozenset({"office"}), city="Москва"
    )
    same_city = match_candidate(
        office, candidate(1, work_formats=frozenset({"office"}), city="г. Москва")
    )
    assert "Кандидат в другом городе" not in same_city.reasons
    # Не заполнил город и формат это неизвестность: ни штрафа, ни ложного объяснения.
    unknown = match_candidate(office, candidate(2, work_formats=frozenset(), city=""))
    assert unknown.format_compatible
    assert not any("город" in r or "формат" in r for r in unknown.reasons)
    other = match_candidate(
        office, candidate(3, work_formats=frozenset({"office"}), city="Казань")
    )
    assert "Кандидат в другом городе" in other.reasons
