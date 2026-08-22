import ast
import os
import shutil
import sys
import tomllib
from collections.abc import Iterable
from os import mkdir
from pathlib import Path

import pytest
from click.testing import CliRunner

from sdsort import cli, config, context, main, sort, step_down_sort
from sdsort.cli import _MAX_WORKERS, _MIN_FILES_FOR_PARALLELISM, _worker_count
from sdsort.context import Context, _targets_python314_or_newer
from sdsort.rules import Visibility
from sdsort.utils.file import read_file

TEST_CASES_DIR = Path("test", "cases")
TOML_CASES_DIR = Path("test", "toml_cases")
UNPARSEABLE_SOURCE = "def f(:\n"


def write_unparseable(path: Path) -> Path:
    path.write_text(UNPARSEABLE_SOURCE, encoding="utf-8")
    return path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def unsorted_file(tmp_path: Path) -> Path:
    """A file sdsort will re-arrange. Compare it against the `sorted_output` fixture."""
    return Path(shutil.copy(TEST_CASES_DIR / "comments.in.py", tmp_path))


@pytest.fixture
def already_sorted_file(tmp_path: Path) -> Path:
    """A file already in step-down order, so a run over it reports no changes."""
    return Path(shutil.copy(TEST_CASES_DIR / "comments.out.py", tmp_path))


@pytest.fixture
def unparseable_file(tmp_path: Path) -> Path:
    """A file sdsort cannot parse. Named broken.py, which some assertions match on."""
    return write_unparseable(tmp_path / "broken.py")


@pytest.fixture
def sorted_output() -> str:
    """What the `unsorted_file` fixture's contents look like once sorted."""
    return read_file(TEST_CASES_DIR / "comments.out.py")


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
        "moved_class_with_dependency",
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


@pytest.mark.parametrize(
    "case_name,expected_case_name,visibility_order,sort_by_name",
    [
        (
            "partitioned_methods",
            "partitioned_methods",
            (Visibility.DUNDER, Visibility.PUBLIC, Visibility.PRIVATE, Visibility.PROTECTED),
            True,
        ),
        (
            "partitioned_methods",
            "partitioned_methods_without_name",
            (Visibility.DUNDER, Visibility.PUBLIC, Visibility.PRIVATE, Visibility.PROTECTED),
            False,
        ),
        (
            "visibility_and_name_dependency_chain",
            "visibility_and_name_dependency_chain",
            (Visibility.PRIVATE, Visibility.PUBLIC, Visibility.PROTECTED, Visibility.DUNDER),
            True,
        ),
        (
            "visibility_and_name_cross_partition_dependencies",
            "visibility_and_name_cross_partition_dependencies",
            (Visibility.PUBLIC, Visibility.PROTECTED, Visibility.PRIVATE, Visibility.DUNDER),
            True,
        ),
        (
            "async_methods_with_visibility_and_name",
            "async_methods_with_visibility_and_name",
            (Visibility.DUNDER, Visibility.PRIVATE, Visibility.PROTECTED, Visibility.PUBLIC),
            True,
        ),
        (
            "overloads_with_visibility_and_name",
            "overloads_with_visibility_and_name",
            (Visibility.DUNDER, Visibility.PRIVATE, Visibility.PROTECTED, Visibility.PUBLIC),
            True,
        ),
        (
            "visibility_and_name_recursive_methods",
            "visibility_and_name_recursive_methods",
            (Visibility.DUNDER, Visibility.PRIVATE, Visibility.PROTECTED, Visibility.PUBLIC),
            True,
        ),
        ("partial_visibility_ranks", "partial_visibility_ranks", (Visibility.DUNDER, Visibility.PRIVATE), False),
        ("partial_visibility_ranks", "partial_visibility_ranks", (Visibility.DUNDER,), False),
        (
            "partial_visibility_ranks",
            "partial_visibility_ranks_by_name",
            (Visibility.DUNDER, Visibility.PRIVATE),
            True,
        ),
    ],
)
def test_visibility_and_name_cases(
    monkeypatch: pytest.MonkeyPatch,
    case_name: str,
    expected_case_name: str,
    visibility_order: Iterable[Visibility],
    sort_by_name: bool,
) -> None:
    def configured_context(_root: ast.Module, _path: Path | None = None) -> Context:
        return Context(
            deferred_annotations=False,
            config=config.from_table({"method-order": ["visibility"], "visibility-order": visibility_order}),
            sort_by_name=sort_by_name,
        )

    monkeypatch.setattr(sort, "gather_context", configured_context)
    _, actual_output = step_down_sort(TEST_CASES_DIR / f"{case_name}.in.py")

    assert actual_output == read_file(TEST_CASES_DIR / f"{expected_case_name}.out.py")


@pytest.mark.parametrize(
    "case_name",
    [
        "full_ranks",
        "partial_ranks",
        "partial_ranks_by_name",
        "no_ranks_by_name",
        "no_ranks_by_name_with_dependencies",
        "no_ranks_by_name_complex",
    ],
)
def test_toml_configuration_cases(case_name: str):
    case_dir = TOML_CASES_DIR / case_name

    status, actual_output = step_down_sort(case_dir / "input.py")
    assert status == "sorted"
    assert actual_output == read_file(case_dir / "expected.py")


def test_pyproject_is_parsed_once_per_project(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    source_paths = (tmp_path / "first.py", tmp_path / "second.py")
    for source_path in source_paths:
        source_path.write_text("def function():\n    pass\n", encoding="utf-8")

    context._load_pyproject.cache_clear()
    for source_path in source_paths:
        step_down_sort(source_path)
    assert context._load_pyproject.cache_info().misses == 1


@pytest.mark.skipif(sys.version_info < (3, 12), reason="`type` alias statement requires Python 3.12+")
def test_type_alias_is_not_reordered_below_class_it_references():
    input_file_path = TEST_CASES_DIR / "type_declaration.in.py"
    expected_output = read_file(TEST_CASES_DIR / "type_declaration.out.py")

    _, actual_output = step_down_sort(input_file_path)

    if actual_output is None:
        actual_output = read_file(input_file_path)
    assert actual_output == expected_output


def test_when_single_file_is_targeted_then_other_files_are_not_modified(
    tmp_path: Path, runner: CliRunner, unsorted_file: Path, sorted_output: str
):
    # Arrange
    other_file = TEST_CASES_DIR / "dataclass.in.py"
    other_path = shutil.copy(other_file, tmp_path)

    # Act
    runner.invoke(main, [str(unsorted_file)])

    # Assert
    assert read_file(unsorted_file) == sorted_output, "Target file should be sorted"
    assert read_file(other_path) == read_file(other_file), "Other file should be unchanged"


def test_when_directory_is_provided_then_all_python_files_in_it_are_sorted(tmp_path: Path, runner: CliRunner):
    # Arrange
    test_cases = ["comments", "dataclass"]

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


def test_check_flag_reports_unsorted_files_without_modifying_them(runner: CliRunner, unsorted_file: Path):
    # Arrange
    original_content = read_file(unsorted_file)

    # Act
    result = runner.invoke(main, ["--check", str(unsorted_file)])

    # Assert
    assert result.exit_code == 1, "Exit code should be 1 when files need sorting"
    assert "would be re-arranged" in result.output
    assert read_file(unsorted_file) == original_content, "File should not be modified"


def test_check_flag_exits_cleanly_when_files_are_already_sorted(runner: CliRunner, already_sorted_file: Path):
    # Act
    result = runner.invoke(main, ["--check", str(already_sorted_file)])

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
    txt = f'[project]\nrequires-python = "{requires_python}"\n'
    assert _targets_python314_or_newer(tomllib.loads(txt)) is expected


@pytest.mark.parametrize(
    "file_count,jobs,cpu_count,expected",
    [
        (1000, 0, 4, 4),  # auto: one worker per available CPU
        (1000, 1, 4, 1),  # explicit -j 1 disables parallelism
        (1000, 3, 4, 3),  # explicit job count is honoured
        (_MIN_FILES_FOR_PARALLELISM - 1, 0, 4, 1),  # too little work to be worth spawning workers
        (_MIN_FILES_FOR_PARALLELISM, 0, 4, 4),
        (2, 8, 4, 2),  # never more workers than files
        (0, 8, 4, 1),  # no files at all must not ask for zero workers
        (10_000, 5000, 4, _MAX_WORKERS),  # an oversized explicit -j degrades gracefully
        (10_000, 0, 200, _MAX_WORKERS),  # the ceiling applies to a detected count too
    ],
)
def test_worker_count(file_count: int, jobs: int, cpu_count: int, expected: int):
    assert _worker_count(file_count, jobs, cpu_count) == expected


def test_parallel_run_matches_serial_run(tmp_path: Path, runner: CliRunner):
    # Sorting happens in worker processes, so verify that route writes exactly what the
    # single-process route does.
    test_cases = ["comments", "dataclass", "single_class", "top_level_functions"]
    serial_dir = tmp_path / "serial"
    parallel_dir = tmp_path / "parallel"
    for directory in (serial_dir, parallel_dir):
        mkdir(directory)
        for tc in test_cases:
            shutil.copy(TEST_CASES_DIR / f"{tc}.in.py", directory)

    serial_result = runner.invoke(main, ["-j", "1", str(serial_dir)])
    parallel_result = runner.invoke(main, ["-j", "4", str(parallel_dir)])

    assert serial_result.exit_code == 0, serial_result.output
    assert parallel_result.exit_code == 0, parallel_result.output
    for tc in test_cases:
        expected = read_file(TEST_CASES_DIR / f"{tc}.out.py")
        assert read_file(serial_dir / f"{tc}.in.py") == expected
        assert read_file(parallel_dir / f"{tc}.in.py") == expected, f"{tc} differs when sorted in parallel"


def test_unparseable_file_does_not_abort_the_run(
    tmp_path: Path, runner: CliRunner, unparseable_file: Path, unsorted_file: Path, sorted_output: str
):
    # A file sdsort cannot parse must not stop the files after it from being sorted.
    result = runner.invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert read_file(unsorted_file) == sorted_output
    assert read_file(unparseable_file) == UNPARSEABLE_SOURCE, "Unparseable file must be left alone"


def test_file_that_is_not_valid_utf8_is_skipped(tmp_path: Path, runner: CliRunner):
    latin1_source = b"# caf\xe9\ndef f():\n    return 1\n"
    target_path = tmp_path / "latin1.py"
    target_path.write_bytes(latin1_source)

    result = runner.invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "1 file could not be parsed" in result.stderr, "The file must be reported, not silently passed over"
    assert target_path.read_bytes() == latin1_source


@pytest.mark.usefixtures("unparseable_file", "already_sorted_file")
def test_check_exits_zero_when_the_only_problem_is_an_unparseable_file(tmp_path: Path, runner: CliRunner):
    result = runner.invoke(main, ["--check", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "1 file could not be parsed" in result.stderr


@pytest.mark.usefixtures("unparseable_file", "unsorted_file")
def test_check_still_exits_one_when_a_sortable_file_would_be_rearranged(tmp_path: Path, runner: CliRunner):
    result = runner.invoke(main, ["--check", str(tmp_path)])
    assert result.exit_code == 1, result.output


@pytest.mark.usefixtures("unparseable_file", "already_sorted_file")
def test_unparseable_files_are_reported_on_stderr(tmp_path: Path, runner: CliRunner):
    result = runner.invoke(main, [str(tmp_path)])

    assert "Could not parse the following files:" in result.stderr
    assert "broken.py: invalid syntax (line 1)" in result.stderr
    assert "1 file could not be parsed" in result.stderr
    assert "1 file already sorted" in result.stdout, "Unparseable files must not inflate this count"
    assert "Checked 2 files" in result.stdout, "But they are still counted as checked"


def test_parallel_run_reports_the_same_warnings_as_serial(tmp_path: Path, runner: CliRunner):
    for name in ("broken_one.py", "broken_two.py"):
        write_unparseable(tmp_path / name)

    serial = runner.invoke(main, ["-j", "1", str(tmp_path)])
    parallel = runner.invoke(main, ["-j", "4", str(tmp_path)])

    assert serial.stderr == parallel.stderr
    assert "broken_one.py" in serial.stderr
    assert "broken_two.py" in serial.stderr


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


@pytest.mark.usefixtures("unsorted_file")
def test_non_tolerated_exception_still_crashes_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, runner: CliRunner
):
    def _raise(_path: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "step_down_sort", _raise)

    with pytest.raises(RuntimeError, match="boom"):
        runner.invoke(main, ["-j", "1", str(tmp_path)], catch_exceptions=False)


def test_write_failure_after_a_successful_sort_still_crashes(
    tmp_path: Path, runner: CliRunner, unsorted_file: Path
):
    # Only *read*/*parse* failures are tolerated. If sorting succeeds but
    # writing the result back fails, that must still crash the run rather than being swallowed.
    # Make the the file read-only to trigger a write failure
    os.chmod(unsorted_file, 0o444)
    with pytest.raises(OSError):
        runner.invoke(main, ["-j", "1", str(tmp_path)], catch_exceptions=False)
