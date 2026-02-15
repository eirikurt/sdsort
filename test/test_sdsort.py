import shutil
import tempfile
from os import mkdir, path

import pytest
from click.testing import CliRunner

from sdsort import main, step_down_sort

TEST_CASES_DIR = "test/cases"


@pytest.mark.parametrize(
    "test_case,",
    [
        "single_class",
        "comments",
        "circular",
        "nested_class",
        "nested_function",
        "dataclass",
        "top_level_functions",
        "top_level_with_invocation",
        "mixed_class_and_functions",
        "function_decorator",
        "async_functions",
        "circular_functions",
        "multiple_barriers",
        "pytest_fixtures",
    ],
)
def test_all_cases(test_case: str):
    # Arrange
    input_file_path = f"{TEST_CASES_DIR}/{test_case}.in.py"
    expected_output_file_path = f"{TEST_CASES_DIR}/{test_case}.out.py"
    expected_output = read_file(expected_output_file_path)

    # Act
    actual_output = step_down_sort(input_file_path)

    if actual_output is None:
        actual_output = read_file(input_file_path)
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


def test_when_directory_is_provided_then_all_python_files_in_it_are_sorted():
    # Arrange
    test_cases = ["comments", "dataclass"]
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy a couple of files
        for tc in test_cases:
            shutil.copy(f"{TEST_CASES_DIR}/{tc}.in.py", temp_dir)

        subdir_path = path.join(temp_dir, "subdir")
        mkdir(subdir_path)
        subdir_file_path = shutil.copy(f"{TEST_CASES_DIR}/single_class.in.py", subdir_path)

        # Act
        runner.invoke(main, [temp_dir])

        # Files back
        files_after = {tc: read_file(path.join(temp_dir, f"{tc}.in.py")) for tc in test_cases}
        files_after["single_class"] = read_file(subdir_file_path)

    # Assert
    for tc, file_after in files_after.items():
        assert file_after == read_file(f"{TEST_CASES_DIR}/{tc}.out.py")
    # TODO: assert that other files in directory were not modified?


def test_check_flag_reports_unsorted_files_without_modifying_them():
    # Arrange
    file_to_sort = f"{TEST_CASES_DIR}/comments.in.py"
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        target_path = shutil.copy(file_to_sort, temp_dir)
        original_content = read_file(target_path)

        # Act
        result = runner.invoke(main, ["--check", target_path])

        # Assert
        assert result.exit_code == 1, "Exit code should be 1 when files need sorting"
        assert "would be re-arranged" in result.output
        assert read_file(target_path) == original_content, "File should not be modified"


def test_check_flag_exits_cleanly_when_files_are_already_sorted():
    # Arrange
    already_sorted_file = f"{TEST_CASES_DIR}/comments.out.py"
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        target_path = shutil.copy(already_sorted_file, temp_dir)

        # Act
        result = runner.invoke(main, ["--check", target_path])

        # Assert
        assert result.exit_code == 0, "Exit code should be 0 when files are already sorted"
        assert "would be re-arranged" not in result.output


def read_file(file_path: str) -> str:
    with open(file_path) as file:
        return file.read()
