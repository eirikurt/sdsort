import pytest
from sut import _calculate_score 


def generate_test_case(scenario: str):
    return str(reversed(scenario))


@pytest.mark.parametrize(
    "task,expected_score",
    [
        (generate_test_case("easy"), 95),
        (generate_test_case("medium"), 75),
        (generate_test_case("hard"), 65),
    ],
)
def test__calculate_score(
    task: str,
    expected_score: int,
):
    # Act
    score = _calculate_score(task)

    # Assert
    assert score == expected_score
