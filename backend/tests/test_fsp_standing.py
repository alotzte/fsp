from datetime import date

from app.services.db.models import FspAward, FspDiscipline, FspEvent, FspResult
from app.services.fsp import NO_FSP, fsp_standing

TODAY = date(2026, 10, 6)


def result(award: FspAward, starts_on: date = TODAY) -> FspResult:
    event = FspEvent(title="Чемпионат", discipline=FspDiscipline.PRODUCT, starts_on=starts_on)
    return FspResult(award=award, fsp_id="FSP-1", event=event)


def test_participation_alone_gives_nothing() -> None:
    """Организаторы: учитывать результаты, а не участие."""
    standing = fsp_standing([result(FspAward.PARTICIPANT)] * 5, TODAY)
    assert standing == NO_FSP


def test_results_count_and_saturate() -> None:
    one = fsp_standing([result(FspAward.WINNER)], TODAY)
    two = fsp_standing([result(FspAward.WINNER), result(FspAward.PRIZE)], TODAY)
    finalist = fsp_standing([result(FspAward.FINALIST)], TODAY)
    assert 0 < finalist.score < one.score < two.score < 1
    assert (one.achievements, two.achievements, finalist.achievements) == (1, 2, 1)


def test_old_results_weigh_less() -> None:
    fresh = fsp_standing([result(FspAward.WINNER)], TODAY)
    old = fsp_standing([result(FspAward.WINNER, date(2022, 10, 6))], TODAY)
    assert old.score < fresh.score


def test_relevant_discipline_counts_but_weighs_the_same() -> None:
    """Эксперты: ИБ-специалисту соревнования по ИБ релевантнее робототехники. Это строка
    объяснения, а не вес: все соревнования весят одинаково."""
    infosec = result(FspAward.WINNER)
    infosec.event.discipline = FspDiscipline.INFOSEC
    robotics = result(FspAward.WINNER)
    robotics.event.discipline = FspDiscipline.ROBOTICS
    standing = fsp_standing([infosec, robotics], TODAY, "security")
    assert (standing.achievements, standing.relevant) == (2, 1)
    assert standing.score == fsp_standing([infosec, robotics], TODAY, "embedded").score
    assert fsp_standing([infosec], TODAY).relevant == 0
