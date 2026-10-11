import uuid

from app.services.invitations import from_my_side

CANDIDATE = uuid.uuid4()
RECRUITER = uuid.uuid4()


def test_candidate_message_is_mine_only_for_candidate() -> None:
    assert from_my_side(CANDIDATE, CANDIDATE, viewer_is_candidate=True)
    assert not from_my_side(CANDIDATE, CANDIDATE, viewer_is_candidate=False)


def test_colleague_message_is_company_side() -> None:
    # Сообщение другого сотрудника: своё для компании, а не сообщение кандидата.
    assert from_my_side(RECRUITER, CANDIDATE, viewer_is_candidate=False)
    assert not from_my_side(RECRUITER, CANDIDATE, viewer_is_candidate=True)
    # Автор удалён (SET NULL): это мог быть только сотрудник компании.
    assert from_my_side(None, CANDIDATE, viewer_is_candidate=False)
