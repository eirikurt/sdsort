import ast
import os
import shutil
import sys
from os import mkdir
from pathlib import Path

import pytest
from click.testing import CliRunner

from sdsort import main, step_down_sort
from sdsort.cli import _MIN_FILES_FOR_PARALLELISM, _worker_count
from sdsort.context import _targets_python314_or_newer
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
        "overloads",
        "type_hints",
        "jpe",
        "multiline_string",
        "circular_class",
        "statement_references_later_definition",
        "flask_tag",
        "partial_function",
        "class_attribute_name_collision",
        "class_attribute_references_outer_function",
        "dangling_comment_between_defs",
        "deferred_class_attribute_annotations",
        "deferred_statement_annotation",
        "skip_file_directive",
    ],
)
def test_all_cases(test_case: str):
    # Arrange
    input_file_path = TEST_CASES_DIR / f"{test_case}.in.py"
    expected_output_file_path = TEST_CASES_DIR / f"{test_case}.out.py"
    expected_output = read_file(expected_output_file_path)

    # Act
    _, actual_output = step_down_sort(input_file_path)

    if actual_output is None:
        actual_output = read_file(input_file_path)
    assert actual_output == expected_output


@pytest.mark.skipif(sys.version_info < (3, 12), reason="`type` alias statement requires Python 3.12+")
def test_type_alias_is_not_reordered_below_class_it_references():
    input_file_path = TEST_CASES_DIR / "type_declaration.in.py"
    expected_output = read_file(TEST_CASES_DIR / "type_declaration.out.py")

    _, actual_output = step_down_sort(input_file_path)

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


@pytest.mark.parametrize(
    "requires_python,expected",
    [
        (">=3.11", False),
        (">=3.13", False),
        (">=3.14", True),
        (">=3.14.0", True),
        (">=3.14a1", True),  # PEP 440 pre-release specifier must not crash int()
        (">=3.15b2", True),
    ],
)
def test_targets_python314_handles_prerelease_specifiers(tmp_path: Path, requires_python: str, expected: bool):
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nrequires-python = "{requires_python}"\n', encoding="utf-8"
    )
    assert _targets_python314_or_newer(tmp_path) is expected


@pytest.mark.parametrize(
    "file_count,jobs,expected",
    [
        (1000, 0, os.cpu_count() or 1),  # auto: one worker per CPU
        (1000, 1, 1),  # explicit -j 1 disables parallelism
        (1000, 3, 3),  # explicit job count is honoured
        (_MIN_FILES_FOR_PARALLELISM - 1, 0, 1),  # too little work to be worth spawning workers
        (_MIN_FILES_FOR_PARALLELISM, 0, os.cpu_count() or 1),
        (2, 8, 2),  # never more workers than files
        (0, 8, 1),  # no files at all must not ask for zero workers
    ],
)
def test_worker_count(file_count: int, jobs: int, expected: int):
    assert _worker_count(file_count, jobs) == expected


def test_parallel_run_matches_serial_run(tmp_path: Path):
    # Sorting happens in worker processes, so verify that route writes exactly what the
    # single-process route does.
    test_cases = ["comments", "dataclass", "single_class", "top_level_functions"]
    serial_dir = tmp_path / "serial"
    parallel_dir = tmp_path / "parallel"
    for directory in (serial_dir, parallel_dir):
        mkdir(directory)
        for tc in test_cases:
            shutil.copy(TEST_CASES_DIR / f"{tc}.in.py", directory)

    runner = CliRunner()
    serial_result = runner.invoke(main, ["-j", "1", str(serial_dir)])
    parallel_result = runner.invoke(main, ["-j", "4", str(parallel_dir)])

    assert serial_result.exit_code == 0, serial_result.output
    assert parallel_result.exit_code == 0, parallel_result.output
    for tc in test_cases:
        expected = read_file(TEST_CASES_DIR / f"{tc}.out.py")
        assert read_file(serial_dir / f"{tc}.in.py") == expected
        assert read_file(parallel_dir / f"{tc}.in.py") == expected, f"{tc} differs when sorted in parallel"


def test_form_feed_between_functions_does_not_crash(tmp_path: Path):
    # A form feed (\x0c) is in-line whitespace to Python's tokenizer, but str.splitlines()
    # treats it as a line break. Splitting on it misaligns line ranges from AST line numbers.
    source = "def helper():\n    return 1\n\n\x0c\n\ndef main():\n    return helper()\n"
    target_path = tmp_path / "form_feed.py"
    target_path.write_text(source, encoding="utf-8")

    # Act
    status, output = step_down_sort(target_path)

    # Assert
    assert status == "sorted"
    assert output is not None
    tree = ast.parse(output)
    assert {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} == {"helper", "main"}
    assert output.index("def main") < output.index("def helper"), "main should come before helper"
