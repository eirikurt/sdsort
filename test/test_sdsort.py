import shutil
from os import mkdir
from pathlib import Path

import pytest
from click.testing import CliRunner

from sdsort import main, step_down_sort
from sdsort.utils.file import read_file

TEST_CASES_DIR = Path("test", "cases")


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
        "sandwiched_decorator",
        "parametrized_test",
    ],
)
def test_all_cases(test_case: str):
    # Arrange
    input_file_path = TEST_CASES_DIR / f"{test_case}.in.py"
    expected_output_file_path = TEST_CASES_DIR / f"{test_case}.out.py"
    expected_output = read_file(expected_output_file_path)

    # Act
    actual_output = step_down_sort(input_file_path)

    if actual_output is None:
        actual_output = read_file(input_file_path)
    assert actual_output == expected_output


def test_when_single_file_is_targeted_then_other_files_are_not_modified(tmp_path: Path):
    # Arrange
    file_to_sort = TEST_CASES_DIR / "comments.in.py"
    other_file = TEST_CASES_DIR / "dataclass.in.py"
    runner = CliRunner()

    # Copy a couple of files
    target_path = shutil.copy(file_to_sort, tmp_path)
    other_path = shutil.copy(other_file, tmp_path)

    # Act
    runner.invoke(main, [str(target_path)])

    # read both back
    target_after = read_file(target_path)
    other_after = read_file(other_path)

    # Assert
    assert target_after == read_file(TEST_CASES_DIR / "comments.out.py"), "Target file should be sorted"
    assert other_after == read_file(other_file), "Other file should be unchanged"


def test_when_directory_is_provided_then_all_python_files_in_it_are_sorted(tmp_path: Path):
    # Arrange
    test_cases = ["comments", "dataclass"]
    runner = CliRunner()

    # Copy a couple of files
    for tc in test_cases:
        shutil.copy(TEST_CASES_DIR / f"{tc}.in.py", tmp_path)

    subdir_path = tmp_path / "subdir"
    mkdir(subdir_path)
    subdir_file_path = shutil.copy(TEST_CASES_DIR / "single_class.in.py", subdir_path)

    # Act
    runner.invoke(main, [str(tmp_path)])

    # Files back
    files_after = {tc: read_file(tmp_path / f"{tc}.in.py") for tc in test_cases}
    files_after["single_class"] = read_file(subdir_file_path)

    # Assert
    for tc, file_after in files_after.items():
        assert file_after == read_file(TEST_CASES_DIR / f"{tc}.out.py")
    # TODO: assert that other files in directory were not modified?


def test_check_flag_reports_unsorted_files_without_modifying_them(tmp_path: Path):
    # Arrange
    file_to_sort = TEST_CASES_DIR / "comments.in.py"
    runner = CliRunner()

    target_path = shutil.copy(file_to_sort, tmp_path)
    original_content = read_file(target_path)

    # Act
    result = runner.invoke(main, ["--check", str(target_path)])

    # Assert
    assert result.exit_code == 1, "Exit code should be 1 when files need sorting"
    assert "would be re-arranged" in result.output
    assert read_file(target_path) == original_content, "File should not be modified"


def test_check_flag_exits_cleanly_when_files_are_already_sorted(tmp_path: Path):
    # Arrange
    already_sorted_file = TEST_CASES_DIR / "comments.out.py"
    runner = CliRunner()

    target_path = shutil.copy(already_sorted_file, tmp_path)

    # Act
    result = runner.invoke(main, ["--check", str(target_path)])

    # Assert
    assert result.exit_code == 0, "Exit code should be 0 when files are already sorted"
    assert "would be re-arranged" not in result.output
