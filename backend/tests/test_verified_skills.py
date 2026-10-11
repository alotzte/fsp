from app.services.hiring import CompetencyResult, verified_skill_slugs


def result(competency: str, correct: int, total: int) -> CompetencyResult:
    return CompetencyResult(competency, competency, correct, total)


def test_half_correct_with_two_items_verifies_skill() -> None:
    assert verified_skill_slugs([result("python", 2, 4), result("js", 1, 2)]) == {
        "python",
        "javascript",
    }


def test_below_share_or_single_item_stays_claimed() -> None:
    assert verified_skill_slugs([result("sql", 1, 4), result("react", 1, 1)]) == set()


def test_competency_without_dictionary_skill_is_ignored() -> None:
    assert verified_skill_slugs([result("http_api", 3, 3), result("stats", 4, 4)]) == set()
