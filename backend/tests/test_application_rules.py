from app.services.invitations import (
    APPLICATIONS_PER_WEEK,
    ApplicationGradeMismatchError,
    ApplicationWeeklyLimitError,
    application_block,
)

MIDDLE = 2


def test_confirmed_grade_applies_to_own_and_neighbour_grades() -> None:
    for vacancy in (1, 2, 3):
        assert (
            application_block(confirmed_level=MIDDLE, vacancy_level=vacancy, applied_this_week=50)
            is None
        )


def test_confirmed_grade_cannot_jump_two_grades() -> None:
    for vacancy in (0, 4):
        assert (
            application_block(confirmed_level=MIDDLE, vacancy_level=vacancy, applied_this_week=0)
            is ApplicationGradeMismatchError
        )


def test_unconfirmed_grade_is_limited_per_week_but_not_by_grade() -> None:
    assert application_block(confirmed_level=None, vacancy_level=4, applied_this_week=0) is None
    assert (
        application_block(
            confirmed_level=None, vacancy_level=1, applied_this_week=APPLICATIONS_PER_WEEK - 1
        )
        is None
    )
    assert (
        application_block(
            confirmed_level=None, vacancy_level=1, applied_this_week=APPLICATIONS_PER_WEEK
        )
        is ApplicationWeeklyLimitError
    )
