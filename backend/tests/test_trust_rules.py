from app.services.trust import (
    FREEZE_AFTER_REPORTS,
    email_matches_website,
    pending_quota,
    should_freeze,
    website_domain,
)


def test_new_company_has_smaller_quota() -> None:
    assert pending_quota(0) < pending_quota(1)
    # Уровень выше известных (например, проверка ИНН в будущем): не меньше максимальной квоты.
    assert pending_quota(5) == pending_quota(1)


def test_freeze_after_reports_from_different_candidates() -> None:
    assert not should_freeze(FREEZE_AFTER_REPORTS - 1)
    assert should_freeze(FREEZE_AFTER_REPORTS)


def test_website_domain() -> None:
    assert website_domain("https://www.Acme.ru/about") == "acme.ru"
    assert website_domain("") is None
    assert website_domain("не сайт") is None


def test_email_must_be_in_website_domain() -> None:
    site = "https://acme.ru"
    assert email_matches_website("hr@acme.ru", site)
    assert email_matches_website("hr@mail.acme.ru", site)
    assert not email_matches_website("hr@notacme.ru", site)
    assert not email_matches_website("hr@acme.ru.evil.com", site)
    assert not email_matches_website("hr@gmail.com", site)
    assert not email_matches_website("hr@acme.ru", "")
