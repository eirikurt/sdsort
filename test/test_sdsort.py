# TODO: add test cases for
# - dataclass
import pytest

from sdsort import step_down_sort

TEST_CASES_DIR = "test/cases"


@pytest.mark.parametrize("test_case,", ["single_class", "comments", "circular", "nested_class", "nested_function"])
def test_all_cases(test_case: str):
    # Arrange
    input_file_path = f"{TEST_CASES_DIR}/{test_case}.in.py"
    expected_output_file_path = f"{TEST_CASES_DIR}/{test_case}.out.py"
    expected_output = read_file(expected_output_file_path)

    # Act
    actual_output = step_down_sort(input_file_path)

    assert actual_output == expected_output


def read_file(file_path: str) -> str:
    with open(file_path) as file:
        return file.read()
