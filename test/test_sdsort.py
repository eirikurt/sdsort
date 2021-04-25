import shutil
import tempfile

import pytest
from click.testing import CliRunner

from sdsort import main, step_down_sort

TEST_CASES_DIR = "test/cases"


@pytest.mark.parametrize(
    "test_case,", ["single_class", "comments", "circular", "nested_class", "nested_function", "dataclass"]
)
def test_all_cases(test_case: str):
    # Arrange
    input_file_path = f"{TEST_CASES_DIR}/{test_case}.in.py"
    expected_output_file_path = f"{TEST_CASES_DIR}/{test_case}.out.py"
    expected_output = read_file(expected_output_file_path)

    # Act
    actual_output = step_down_sort(input_file_path)

    assert actual_output == expected_output


def test_when_single_file_is_targeted_then_other_files_are_not_modified():
    # Arrange
    file_to_sort = f"{TEST_CASES_DIR}/comments.in.py"
    other_file = f"{TEST_CASES_DIR}/dataclass.in.py"
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy a couple of files
        target_path = shutil.copy(file_to_sort, temp_dir)
        other_path = shutil.copy(other_file, temp_dir)

        # Act
        runner.invoke(main, [target_path])

        # read both back
        target_after = read_file(target_path)
        other_after = read_file(other_path)

    # Assert
    assert target_after == read_file(f"{TEST_CASES_DIR}/comments.out.py"), "Target file should be sorted"
    assert other_after == read_file(other_file), "Other file should be unchanged"


def read_file(file_path: str) -> str:
    with open(file_path) as file:
        return file.read()
