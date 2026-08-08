# Unparseable File Warnings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A file sdsort cannot parse is reported and skipped instead of aborting the whole run.

**Architecture:** The error boundary lives in the CLI worker function `_sort_file`, not in
`step_down_sort`. The library keeps raising, so `test/smoke_test.py` continues to catch sdsort
defects. `_sort_file` catches only parse and read errors, formats the reason into a plain string
inside the worker (so nothing but `str` crosses the process-pool boundary), and returns it as a
new `"unparseable"` outcome. The CLI collects these into a new `Results` bucket and prints them
as a grouped section on stderr.

**Tech Stack:** Python 3.11+, Click 8.3, pytest, ruff, pyright (strict).

**Spec:** `docs/superpowers/specs/2026-08-08-unparseable-file-warnings-design.md`

## Global Constraints

- Exit code must be unchanged by unparseable files. `--check` exits 1 only when files would be
  re-arranged.
- Catch exactly `SyntaxError`, `tokenize.TokenError`, `UnicodeDecodeError`, `OSError`. Every other
  exception, `RecursionError` included, must still propagate and crash the run.
- Only the `step_down_sort` call is wrapped. The write-back in `_sort_file` stays outside the
  `try`, so a failing write still crashes. This is deliberate, per the spec's non-goals.
- Warning output goes to stderr via `click.secho(..., err=True)`. Everything else keeps its
  current stream.
- Line length 115 (ruff). Pyright runs in strict mode and must report 0 errors.
- Run `make rpt` (ruff → pyright → pytest) before every commit.
- The repository is on branch `perf/cut-per-file-work`. Keep committing there.

---

### Task 1: Skip unparseable files instead of aborting

Behaviour only. After this task a broken file no longer crashes the run and no longer appears in
any count; the user-visible warning section arrives in Task 2.

**Files:**

- Modify: `sdsort/cli.py`
- Test: `test/test_sdsort.py`

**Interfaces:**

- Consumes: `step_down_sort(path) -> ResultType` from `sdsort/sort.py`, unchanged.
- Produces:
  - `FileOutcome` type alias in `sdsort/cli.py`.
  - `_describe_failure(error: Exception) -> str`.
  - `_sort_file(file_path: str, check: bool) -> FileOutcome` (was `-> str`).
  - `_sort_each(...) -> Iterator[FileOutcome]` (was `Iterator[str]`).
  - `Results.unparseable_files: list[tuple[str, str]]` holding `(file_path, reason)` pairs.

- [ ] **Step 1: Write the failing tests**

Add to `test/test_sdsort.py`, after `test_parallel_run_matches_serial_run`:

```python
def test_unparseable_file_does_not_abort_the_run(tmp_path: Path):
    # A file sdsort cannot parse must not stop the files after it from being sorted.
    (tmp_path / "broken.py").write_text("def f(:\n", encoding="utf-8")
    shutil.copy(TEST_CASES_DIR / "comments.in.py", tmp_path)
    runner = CliRunner()

    result = runner.invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert read_file(tmp_path / "comments.in.py") == read_file(TEST_CASES_DIR / "comments.out.py")
    assert read_file(tmp_path / "broken.py") == "def f(:\n", "Unparseable file must be left alone"


def test_file_that_is_not_valid_utf8_is_skipped(tmp_path: Path):
    target_path = tmp_path / "latin1.py"
    target_path.write_bytes(b"# caf\xe9\ndef f():\n    return 1\n")
    runner = CliRunner()

    result = runner.invoke(main, [str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert target_path.read_bytes() == b"# caf\xe9\ndef f():\n    return 1\n"


def test_check_exits_zero_when_the_only_problem_is_an_unparseable_file(tmp_path: Path):
    (tmp_path / "broken.py").write_text("def f(:\n", encoding="utf-8")
    shutil.copy(TEST_CASES_DIR / "comments.out.py", tmp_path)
    runner = CliRunner()

    result = runner.invoke(main, ["--check", str(tmp_path)])

    assert result.exit_code == 0, result.output


def test_check_still_exits_one_when_a_sortable_file_would_be_rearranged(tmp_path: Path):
    # An unparseable file must not mask a genuine --check failure.
    (tmp_path / "broken.py").write_text("def f(:\n", encoding="utf-8")
    shutil.copy(TEST_CASES_DIR / "comments.in.py", tmp_path)
    runner = CliRunner()

    result = runner.invoke(main, ["--check", str(tmp_path)])

    assert result.exit_code == 1, result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_sdsort.py -k "unparseable or utf8 or exits_zero or exits_one" -v`

Expected: FAIL. `test_unparseable_file_does_not_abort_the_run` and the two `--check` tests fail
because `SyntaxError` escapes `_sort_file`; the UTF-8 test fails on `UnicodeDecodeError`. Click's
`CliRunner` catches the exception and reports `exit_code == 1`, so the assertion on `exit_code`
is what fails.

- [ ] **Step 3: Add the outcome type and the failure formatter**

In `sdsort/cli.py`, extend the imports:

```python
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from glob import glob
from tokenize import TokenError
from typing import Iterable, Iterator, Literal, Union

import click
```

Add below the `_MIN_FILES_FOR_PARALLELISM` constant:

```python
# Only parse and read failures are tolerated. Anything else is a defect in sdsort itself, and a
# crash is the right outcome for that: a per-file warning would leave files quietly unsorted.
_UNREADABLE = (SyntaxError, TokenError, UnicodeDecodeError, OSError)

FileOutcome = Union[
    tuple[Literal["sorted", "skipped", "unchanged"], None],
    tuple[Literal["unparseable"], str],
]
```

Add this function directly above `_sort_file`:

```python
def _describe_failure(error: Exception) -> str:
    """Describe why a file could not be read, for display next to its path.

    str(SyntaxError) appends ast's placeholder filename -- "invalid syntax (<unknown>, line 1)" --
    which is noise when the real path is already shown alongside the message.
    """
    if isinstance(error, SyntaxError):
        message = error.msg or "invalid syntax"
        return f"{message} (line {error.lineno})" if error.lineno is not None else message
    return str(error)
```

- [ ] **Step 4: Catch the failure in `_sort_file`**

Replace `_sort_file` in `sdsort/cli.py` with:

```python
def _sort_file(file_path: str, check: bool) -> FileOutcome:
    """Sort a single file, writing it back in place unless this is a --check run.

    This runs inside a worker process, so it writes the file itself rather than shipping the whole
    modified source back to the parent, and it renders the failure reason to a string here so that
    only picklable data crosses the process boundary.
    """
    try:
        modification = step_down_sort(file_path)
    except _UNREADABLE as error:
        return ("unparseable", _describe_failure(error))

    match modification:
        case ("sorted", modified_source):
            if not check:
                with open(file_path, "w", encoding="utf-8") as file:
                    file.write(modified_source)
            return ("sorted", None)
        case ("skipped", _):
            return ("skipped", None)
        case _:
            return ("unchanged", None)
```

Note the write stays outside the `try`, so a failing write still crashes, per the spec.

- [ ] **Step 5: Widen `_sort_each` and record the new outcome**

In `sdsort/cli.py`, change the `_sort_each` signature line from `-> Iterator[str]` to:

```python
def _sort_each(file_paths: list[str], check: bool, jobs: int) -> Iterator[FileOutcome]:
```

Replace the loop body of `_sort_files` so it matches on the outcome tuple:

```python
def _sort_files(file_paths: list[str], check: bool, jobs: int):
    results = Results()

    for file_path, outcome in zip(file_paths, _sort_each(file_paths, check, jobs)):
        match outcome:
            case ("sorted", _):
                results.modified_files.append(file_path)
            case ("skipped", _):
                results.skipped_files.append(file_path)
            case ("unchanged", _):
                results.pristine_files.append(file_path)
            case ("unparseable", reason):
                results.unparseable_files.append((file_path, reason))

    return results
```

Add the bucket to `Results` and count it in the total:

```python
@dataclass
class Results:
    modified_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    pristine_files: list[str] = field(default_factory=list)
    unparseable_files: list[tuple[str, str]] = field(default_factory=list)

    def __len__(self):
        return (
            len(self.modified_files)
            + len(self.pristine_files)
            + len(self.skipped_files)
            + len(self.unparseable_files)
        )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest test/test_sdsort.py -v`

Expected: PASS, 53 passed and 1 skipped. If pyright later objects that `reason` is
`str | None`, the `FileOutcome` union is wrong -- it must be the two-member discriminated union
from Step 3, which narrows `reason` to `str` in the `"unparseable"` arm.

- [ ] **Step 7: Run the full check suite**

Run: `make rpt`

Expected: ruff clean, pyright `0 errors`, all tests pass.

- [ ] **Step 8: Commit**

```bash
git add sdsort/cli.py test/test_sdsort.py
git commit -m "fix: skip files that cannot be parsed instead of aborting the run"
```

---

### Task 2: Report the unparseable files on stderr

**Files:**

- Modify: `sdsort/cli.py`
- Test: `test/test_sdsort.py`

**Interfaces:**

- Consumes: `Results.unparseable_files: list[tuple[str, str]]` from Task 1.
- Produces: no new callable surface; `_print_results` gains a section.

- [ ] **Step 1: Write the failing tests**

Add to `test/test_sdsort.py`:

```python
def test_unparseable_files_are_reported_on_stderr(tmp_path: Path):
    (tmp_path / "broken.py").write_text("def f(:\n", encoding="utf-8")
    shutil.copy(TEST_CASES_DIR / "comments.out.py", tmp_path)
    runner = CliRunner()

    result = runner.invoke(main, [str(tmp_path)])

    assert "Could not parse the following files:" in result.stderr
    # str(SyntaxError) renders as "invalid syntax (broken.py, line 1)", repeating a file name that
    # the line already leads with. The reason must carry the line number without that repetition.
    assert "broken.py: invalid syntax (line 1)" in result.stderr
    assert "1 file could not be parsed" in result.stderr
    assert "1 file already sorted" in result.stdout, "Unparseable files must not inflate this count"
    assert "Checked 2 files" in result.stdout, "But they are still counted as checked"


def test_parallel_run_reports_the_same_warnings_as_serial(tmp_path: Path):
    for name in ("broken_one.py", "broken_two.py"):
        (tmp_path / name).write_text("def f(:\n", encoding="utf-8")
    runner = CliRunner()

    serial = runner.invoke(main, ["-j", "1", str(tmp_path)])
    parallel = runner.invoke(main, ["-j", "4", str(tmp_path)])

    assert serial.stderr == parallel.stderr
    assert "broken_one.py" in serial.stderr
    assert "broken_two.py" in serial.stderr
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_sdsort.py -k "reported_on_stderr or same_warnings" -v`

Expected: FAIL with `AssertionError` on `"Could not parse the following files:" in result.stderr`,
because nothing writes that section yet.

- [ ] **Step 3: Add the report section**

In `sdsort/cli.py`, insert this block into `_print_results`, directly after the
`results.modified_files` block and before the `results.skipped_files` block:

```python
    if len(results.unparseable_files) > 0:
        click.secho("Could not parse the following files:", fg="yellow", bold=True, err=True)
        for unparseable_file, reason in results.unparseable_files:
            click.echo(f"- {unparseable_file}: {reason}", err=True)
        click.secho(
            f"{pluralize(len(results.unparseable_files), 'file')} could not be parsed",
            fg="yellow",
            err=True,
        )
```

- [ ] **Step 4: Correct the `_describe_failure` docstring**

Task 1's docstring justified the formatting with the wrong mechanism. `step_down_sort` calls
`parse(source, filename=python_file_path)`, so `str(SyntaxError)` carries the *real* file name, not
ast's `<unknown>` placeholder. The formatting is still right, but for a different reason. In
`sdsort/cli.py`, replace the second line of the `_describe_failure` docstring:

```python
def _describe_failure(error: Exception) -> str:
    """Describe why a file could not be read, for display next to its path.

    str(SyntaxError) renders as "invalid syntax (broken.py, line 1)", repeating a file name that
    the caller already prints alongside the reason, so the message is rebuilt from its parts.
    """
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest test/test_sdsort.py -v`

Expected: PASS, 55 passed and 1 skipped.

- [ ] **Step 6: Run the full check suite**

Run: `make rpt`

Expected: ruff clean, pyright `0 errors`, all tests pass.

- [ ] **Step 7: Verify against the real-world corpus**

First isolate the exit-code claim. `test/repos/pyochain` contains 26 unparseable files and no
files that need re-arranging, so it is the case where the *only* problem is unparseable files:

```bash
uv run sdsort --check test/repos/pyochain; echo "exit=$?"
```

Expected: `26 files could not be parsed`, `22 files already sorted`, `Checked 48 files`, and
`exit=0`. Before this change the same command died with a `SyntaxError` traceback.

Then run the whole corpus, which the spec requires to produce 74 warnings and zero crashes:

```bash
uv run sdsort --check test/repos; echo "exit=$?"
```

Expected: no traceback, `74 files could not be parsed`, `1700 files already sorted`,
`Checked 1910 files`, and `exit=1`. The exit code is 1 because 136 files in the corpus would be
re-arranged, which is the pre-existing `--check` contract; it is not caused by the 74 warnings.
(These figures are one lower than the 1911/1701 originally recorded here: the CLI's
`_expand_file_paths` uses `glob("**/*.py", recursive=True)`, which does not descend into
dot-directories, so it misses one file that `pathlib.rglob` — used by `test/smoke_test.py` below —
does find.)

Then confirm the other files are unaffected:

```bash
uv run python test/smoke_test.py 2>&1 | tail -3
```

Expected: `files checked: 1911   reordered: 124   failures: 0`, unchanged from before.

- [ ] **Step 8: Commit**

```bash
git add sdsort/cli.py test/test_sdsort.py
git commit -m "feat: report files that could not be parsed"
```

---

### Task 3: Document the behaviour in the README

**Files:**

- Modify: `README.md`

**Interfaces:**

- Consumes: the behaviour built in Tasks 1 and 2.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the note**

In `README.md`, insert this immediately after the paragraph ending
"...making it suitable for CI pipelines and pre-commit hooks." and before the `## Configuration`
heading:

```markdown
### Files that cannot be parsed

If sdsort cannot parse a file, it reports the file on stderr and moves on. The rest of the files
are still sorted, and the exit code is unaffected.

This usually means the file uses newer syntax than the Python interpreter running sdsort, in which
case the file itself is perfectly valid and only sdsort's view of it is limited. Running sdsort
under a newer interpreter resolves it.
```

- [ ] **Step 2: Verify the rendered structure**

Run: `grep -n "^#" README.md`

Expected: the new `### Files that cannot be parsed` appears between the `## Usage` and
`## Configuration` headings, and no heading level was disturbed.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: describe how unparseable files are handled"
```
