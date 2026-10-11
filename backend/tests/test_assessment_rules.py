from datetime import UTC, date, datetime, timedelta

from app.services.assessment import (
    GRADE_CHANGE_COOLDOWN,
    SAME_GRADE_RETRY,
    OptionStatus,
    evaluate_option,
    suggest_grade,
    updates_category_theta,
)
from app.services.db.models import (
    CandidateGrade,
    FspAward,
    FspDiscipline,
    FspEvent,
    FspResult,
)

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)
BACKEND, FRONTEND = 1, 2
JUNIOR, MIDDLE, SENIOR = 11, 12, 13


def category(**fields: object) -> CandidateGrade:
    defaults: dict[str, object] = {"specialization_id": BACKEND, "claimed_grade_id": MIDDLE}
    return CandidateGrade(**(defaults | fields))


def status(
    grade_id: int,
    cat: CandidateGrade | None = None,
    *,
    spec: int = BACKEND,
    failed_at: datetime | None = None,
) -> tuple[OptionStatus, datetime | None]:
    return evaluate_option(
        now=NOW, specialization_id=spec, grade_id=grade_id, category=cat, last_failure_at=failed_at
    )


def test_first_test_any_grade() -> None:
    assert status(SENIOR) == (OptionStatus.AVAILABLE, None)


def test_failed_grade_waits_but_lower_grade_is_immediate() -> None:
    failed_at = NOW - timedelta(days=1)
    cat = category(offered_grade_id=JUNIOR, offer_expires_at=NOW + timedelta(days=6))
    assert status(MIDDLE, cat, failed_at=failed_at) == (
        OptionStatus.COOLDOWN,
        failed_at + SAME_GRADE_RETRY,
    )
    assert status(JUNIOR, cat)[0] == OptionStatus.OFFERED


def test_confirmed_grade_change_is_limited() -> None:
    confirmed_at = NOW - timedelta(days=10)
    cat = category(confirmed_grade_id=MIDDLE, confirmed_at=confirmed_at)
    assert status(MIDDLE, cat)[0] == OptionStatus.CONFIRMED
    for grade, spec in ((SENIOR, BACKEND), (JUNIOR, BACKEND), (MIDDLE, FRONTEND)):
        assert status(grade, cat, spec=spec) == (
            OptionStatus.COOLDOWN,
            confirmed_at + GRADE_CHANGE_COOLDOWN,
        )


def test_upgrade_offer_skips_cooldown_until_it_expires() -> None:
    cat = category(
        confirmed_grade_id=MIDDLE,
        confirmed_at=NOW,
        offered_grade_id=SENIOR,
        offer_expires_at=NOW + timedelta(days=1),
    )
    assert status(SENIOR, cat)[0] == OptionStatus.OFFERED
    assert status(SENIOR, cat, spec=FRONTEND)[0] == OptionStatus.COOLDOWN
    cat.offer_expires_at = NOW - timedelta(seconds=1)
    assert status(SENIOR, cat)[0] == OptionStatus.COOLDOWN


def test_cooldown_ends() -> None:
    cat = category(confirmed_grade_id=MIDDLE, confirmed_at=NOW - GRADE_CHANGE_COOLDOWN)
    assert status(SENIOR, cat) == (OptionStatus.AVAILABLE, None)


# --- подсказка грейда по ФСП -------------------------------------------------------------------


def _fsp(award: FspAward, starts_on: date = date(2026, 6, 1)) -> FspResult:
    event = FspEvent(title="Чемпионат", discipline=FspDiscipline.PRODUCT, starts_on=starts_on)
    return FspResult(award=award, fsp_id="FSP-1", event=event)


FSP_TODAY = date(2026, 10, 7)


def test_no_fsp_history_gives_no_hint() -> None:
    """Без истории ФСП подсказки нет, и ФСП нигде не упоминается (ТЗ, docs/architecture.md §4)."""
    assert suggest_grade([], FSP_TODAY) is None
    assert suggest_grade([_fsp(FspAward.PARTICIPANT)] * 3, FSP_TODAY) is None


def test_fsp_hint_levels() -> None:
    assert suggest_grade([_fsp(FspAward.FINALIST)], FSP_TODAY) == 1
    assert suggest_grade([_fsp(FspAward.PRIZE)], FSP_TODAY) == 2
    assert suggest_grade([_fsp(FspAward.WINNER)], FSP_TODAY) == 2
    assert suggest_grade([_fsp(FspAward.WINNER), _fsp(FspAward.PRIZE)], FSP_TODAY) == 3
    # Два призовых без победы дают Middle: для Senior нужна победа.
    assert suggest_grade([_fsp(FspAward.PRIZE), _fsp(FspAward.PRIZE)], FSP_TODAY) == 2


def test_old_fsp_results_do_not_hint() -> None:
    old = date(2023, 1, 1)
    assert (
        suggest_grade([_fsp(FspAward.WINNER, old), _fsp(FspAward.WINNER, old)], FSP_TODAY) is None
    )


def test_failed_attempt_keeps_confirmed_theta() -> None:
    # Провал на грейд выше подтверждённого не должен опускать кандидата в выдаче.
    assert not updates_category_theta(passed=False, same_specialization=True, has_confirmed=True)
    # Без подтверждённого грейда другой оценки уровня нет: берём эту.
    assert updates_category_theta(passed=False, same_specialization=True, has_confirmed=False)
    assert not updates_category_theta(passed=False, same_specialization=False, has_confirmed=False)
    assert updates_category_theta(passed=True, same_specialization=False, has_confirmed=True)


def test_offer_does_not_skip_retry_pause_after_failure_on_same_grade() -> None:
    # Провал на Middle, затем провал на Senior предлагает Middle снова, но не раньше паузы.
    cat = category(offered_grade_id=MIDDLE, offer_expires_at=NOW + timedelta(days=1))
    assert status(MIDDLE, cat, failed_at=NOW) == (OptionStatus.COOLDOWN, NOW + SAME_GRADE_RETRY)
    assert status(MIDDLE, cat, failed_at=NOW - SAME_GRADE_RETRY)[0] == OptionStatus.OFFERED
