from app.services.invitations import (
    CounterAlreadySentError,
    CounterWithinRangeError,
    counter_block,
)


def test_counter_must_be_above_salary_range() -> None:
    assert counter_block(salary_to_rub=300_000, counter_rub=350_000, already_sent=False) is None
    assert (
        counter_block(salary_to_rub=300_000, counter_rub=300_000, already_sent=False)
        is CounterWithinRangeError
    )


def test_counter_is_sent_once() -> None:
    assert (
        counter_block(salary_to_rub=300_000, counter_rub=400_000, already_sent=True)
        is CounterAlreadySentError
    )
