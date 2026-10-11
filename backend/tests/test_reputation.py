from datetime import UTC, datetime, timedelta

from app.services.invitations import REPUTATION_MIN_INVITATIONS, company_reputation

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


def accepted(days_ago: float, reply_after_hours: float | None) -> tuple[datetime, datetime | None]:
    at = NOW - timedelta(days=days_ago)
    return at, (at + timedelta(hours=reply_after_hours) if reply_after_hours is not None else None)


def test_new_company_has_no_reputation() -> None:
    assert company_reputation(REPUTATION_MIN_INVITATIONS - 1, 0, [], NOW) is None


def test_reply_share_median_and_withdrawn() -> None:
    history = [accepted(10, 4), accepted(9, 20), accepted(8, 80), accepted(7, None)]
    reputation = company_reputation(10, 1, history, NOW)
    assert reputation is not None
    # 80 ч позже окна в 3 дня, а без ответа: не ответила.
    assert reputation.replied_share == 2 / 4
    assert reputation.median_reply == timedelta(hours=20)
    assert reputation.withdrawn_share == 0.1


def test_recent_acceptance_without_reply_is_not_counted_yet() -> None:
    history = [accepted(10, 2), accepted(1, None)]
    reputation = company_reputation(5, 0, history, NOW)
    assert reputation is not None
    assert reputation.replied_share == 1.0
