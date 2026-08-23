import ast
import os
import re
import shutil
import sys
import tomllib
from os import mkdir
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from sdsort import cli, main, pyproject, step_down_sort
from sdsort.cli import _MAX_WORKERS, _MIN_FILES_FOR_PARALLELISM, _worker_count
from sdsort.config import Config, ConfigError
from sdsort.pyproject import _targets_python314_or_newer
from sdsort.utils.file import read_file

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

CASES_DIR = Path("test", "cases")
DEFAULT_CASES_DIR = CASES_DIR / "default"
"""The cases run with no `[tool.sdsort]` table, i.e. against the default configuration."""
MINIMUM_PYTHON_VERSIONS = {
    # The `type` alias statement is a syntax error before 3.12, so this case cannot even be parsed.
    "default/type_declaration": (3, 12),
}
METHOD_ABBREVIATIONS = {"visibility": "v", "dependency": "d", "name": "n"}
VISIBILITY_ABBREVIATIONS = {"dunder": "dun", "public": "pub", "protected": "prot", "private": "priv", "*": "rest"}
UNPARSEABLE_SOURCE = "def f(:\n"


def write_unparseable(path: Path) -> Path:
    path.write_text(UNPARSEABLE_SOURCE, encoding="utf-8")
    return path


def discover_cases():
    """Every `*.in.py`/`*.out.py` pair below `test/cases`, as parameters named "<configuration>/<case>".

    The layout is two levels deep: each subdirectory of `test/cases` holds the pyproject.toml
    under test plus one or more case pairs exercising that configuration. Adding a case is
    therefore a matter of dropping a file pair in, with no test code to touch.
    """
    cases: list[ParameterSet] = []
    for case_dir in sorted(path for path in CASES_DIR.iterdir() if path.is_dir()):
        expected_dir_name = encode_configuration(case_dir)
        assert case_dir.name == expected_dir_name, (
            f"{case_dir} holds the configuration named '{expected_dir_name}'."
            " Rename the directory, or correct the pyproject.toml it does not match."
        )
        cases.extend(discover_cases_in(case_dir))

    unmatched = MINIMUM_PYTHON_VERSIONS.keys() - {case.id for case in cases}
    assert not unmatched, f"MINIMUM_PYTHON_VERSIONS names cases that do not exist: {sorted(unmatched)}"
    return cases


def encode_configuration(case_dir: Path) -> str:
    pyproject_path = case_dir / "pyproject.toml"
    assert pyproject_path.is_file(), f"{case_dir} has no pyproject.toml stating the configuration it tests"
    with pyproject_path.open("rb") as pyproject:
        toml = tomllib.load(pyproject)

    configuration = Config.from_toml(toml)
    if configuration == Config.default():
        return "default"

    method_order = "_".join(METHOD_ABBREVIATIONS[attribute] for attribute in configuration.method_order)
    if "visibility" not in configuration.method_order:
        # Without visibility partitioning, the visibility order never comes into play.
        return method_order
    visibility_order = "_".join(VISIBILITY_ABBREVIATIONS[name] for name in configuration.visibility_order)
    return f"{method_order}__{visibility_order}"


def discover_cases_in(case_dir: Path):
    """The case pairs in one configuration directory, as parameters named "<configuration>/<case>"."""
    cases: list[ParameterSet] = []
    for input_path in sorted(case_dir.glob("*.in.py")):
        case_name = input_path.name.removesuffix(".in.py")
        expected_path = input_path.with_name(f"{case_name}.out.py")
        assert expected_path.is_file(), f"{input_path} has no matching {expected_path.name}"

        case_id = f"{case_dir.name}/{case_name}"
        minimum_version = MINIMUM_PYTHON_VERSIONS.get(case_id)
        cases.append(
            pytest.param(
                input_path,
                expected_path,
                id=case_id,
                marks=[]
                if minimum_version is None
                else [
                    pytest.mark.skipif(
                        sys.version_info < minimum_version,
                        reason=f"requires Python {'.'.join(str(part) for part in minimum_version)}+",
                    )
                ],
            )
        )
    return cases


CASES = discover_cases()


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def unsorted_file(tmp_path: Path) -> Path:
    """A file sdsort will re-arrange. Compare it against the `sorted_output` fixture."""
    return Path(shutil.copy(DEFAULT_CASES_DIR / "comments.in.py", tmp_path))


@pytest.fixture
def already_sorted_file(tmp_path: Path) -> Path:
    """A file already in step-down order, so a run over it reports no changes."""
    return Path(shutil.copy(DEFAULT_CASES_DIR / "comments.out.py", tmp_path))


@pytest.fixture
def unparseable_file(tmp_path: Path) -> Path:
    """A file sdsort cannot parse. Named broken.py, which some assertions match on."""
    return write_unparseable(tmp_path / "broken.py")


@pytest.fixture
def sorted_output() -> str:
    """What the `unsorted_file` fixture's contents look like once sorted."""
    return read_file(DEFAULT_CASES_DIR / "comments.out.py")


@pytest.mark.parametrize("input_path,expected_path", CASES)
def test_cases(input_path: Path, expected_path: Path):
    source = read_file(input_path)
    expected_output = read_file(expected_path)

    status, actual_output = step_down_sort(input_path)

    if source == expected_output:
        # A case whose input is already in step-down order must be left alone.
        assert status in ("unchanged", "skipped"), f"{input_path.name} should not have been rewritten"
        assert actual_output is None
    else:
        assert status == "sorted", f"{input_path.name} should have been rearranged"
        assert actual_output == expected_output


def test_pyproject_is_parsed_once_per_project(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    source_paths = (tmp_path / "first.py", tmp_path / "second.py")
    for source_path in source_paths:
        source_path.write_text("def function():\n    pass\n", encoding="utf-8")

    # XXX: this test should not be poking the innards of the pyproject module
    # TODO: refactor PyProject for observability so this can be avoided
    pyproject._load_table.cache_clear()
    for source_path in source_paths:
        step_down_sort(source_path)
    assert pyproject._load_table.cache_info().misses == 1


def test_when_single_file_is_targeted_then_other_files_are_not_modified(
    tmp_path: Path, runner: CliRunner, unsorted_file: Path, sorted_output: str
):
    # Arrange
    other_file = DEFAULT_CASES_DIR / "dataclass.in.py"
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
        shutil.copy(DEFAULT_CASES_DIR / f"{tc}.in.py", tmp_path)

    subdir_path = tmp_path / "subdir"
    mkdir(subdir_path)
    subdir_file_path = shutil.copy(DEFAULT_CASES_DIR / "single_class.in.py", subdir_path)

    # Act
    runner.invoke(main, [str(tmp_path)])

    # Files back
    files_after = {tc: read_file(tmp_path / f"{tc}.in.py") for tc in test_cases}
    files_after["single_class"] = read_file(subdir_file_path)

    # Assert
    for tc, file_after in files_after.items():
        assert file_after == read_file(DEFAULT_CASES_DIR / f"{tc}.out.py")
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
            shutil.copy(DEFAULT_CASES_DIR / f"{tc}.in.py", directory)

    serial_result = runner.invoke(main, ["-j", "1", str(serial_dir)])
    parallel_result = runner.invoke(main, ["-j", "4", str(parallel_dir)])

    assert serial_result.exit_code == 0, serial_result.output
    assert parallel_result.exit_code == 0, parallel_result.output
    for tc in test_cases:
        expected = read_file(DEFAULT_CASES_DIR / f"{tc}.out.py")
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
    parallel = runner.invoke(main, ["-j", "2", str(tmp_path)])

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


def test_config_error_names_the_pyproject_it_came_from(tmp_path: Path):
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text('[tool.sdsort]\nmethod-order = ["no-such-attribute"]\n', encoding="utf-8")
    source_path = tmp_path / "service.py"
    source_path.write_text("def function():\n    pass\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=re.escape(str(pyproject_path))):
        step_down_sort(source_path)


def test_invalid_configuration_is_reported_and_no_file_is_rewritten(tmp_path: Path, runner: CliRunner):
    (tmp_path / "pyproject.toml").write_text('[tool.sdsort]\nno-such-key = ["dependency"]\n', encoding="utf-8")
    source_path = tmp_path / "service.py"
    original = "def helper():\n    return 1\n\n\ndef caller():\n    return helper()\n"
    source_path.write_text(original, encoding="utf-8")

    result = runner.invoke(main, [str(tmp_path)])

    assert result.exit_code == 1
    assert "invalid sdsort configuration" in result.stderr
    assert "no-such-key" in result.stderr
    assert read_file(source_path) == original, "No file may be rewritten under a configuration sdsort rejected"


def test_invalid_configuration_is_reported_from_worker_processes(tmp_path: Path, runner: CliRunner):
    # The error has to survive being pickled out of a worker process.
    (tmp_path / "pyproject.toml").write_text(
        '[tool.sdsort]\nmethod-order = ["no-such-attribute"]\n', encoding="utf-8"
    )
    for name in ("first.py", "second.py"):
        (tmp_path / name).write_text("def helper():\n    return 1\n\n\ndef caller():\n    return helper()\n")

    result = runner.invoke(main, ["-j", "2", str(tmp_path)])

    assert result.exit_code == 1
    assert "invalid sdsort configuration" in result.stderr
    assert "no-such-attribute" in result.stderr
