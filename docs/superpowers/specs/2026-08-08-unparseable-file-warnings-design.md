# Warn on unparseable files instead of aborting the run

**Date:** 2026-08-08
**Status:** Approved, ready for implementation

## Problem

`_sort_files` in `sdsort/cli.py` calls `step_down_sort` without any error handling, so a single
file that cannot be parsed aborts the entire run with a traceback. Every file after it goes
unsorted, and the user gets a stack trace rather than an actionable message.

This is not a rare edge case. Running sdsort over the ten repositories in `test/repos/`
(1911 files) produces 74 unhandled `SyntaxError`s. They fall into two groups:

| Cause | Count | Example |
| --- | --- | --- |
| Syntax newer than the interpreter running sdsort | ~70 | PEP 695 generics (`expected '('`), PEP 701/750 f-strings |
| Genuinely malformed files | ~4 | Python 2 detection fixtures, deliberately broken test data |

The first group matters most: sdsort running on Python 3.11 cannot parse a file that targets
3.12+, even though the file is perfectly valid for the project that owns it. That is a limitation
of the environment sdsort happens to run in, not a defect in the user's code, and it must not
block their commit.

sdsort cannot reliably distinguish the two groups, so both are treated the same way.

## Goals

- One unparseable file never prevents the remaining files from being sorted.
- The user is told which files were skipped and why.
- Genuine sdsort defects stay loud and remain easy to notice and report.

## Non-goals

- Detecting *why* a file failed to parse, or suggesting a different interpreter version.
- Changing `step_down_sort`'s contract for library consumers. It continues to raise.
- Handling unparseable files in any way other than skipping them.
- Tolerating failures when *writing* a sorted file back. Only the `step_down_sort` call is
  wrapped, so a write that fails (for example, a read-only file) still aborts the run. Reporting
  such a failure under a "could not parse" heading would be actively misleading, and a separate
  outcome for it is scope this change does not need. It remains available as a follow-up.

## Decisions

### Exit code is unaffected

Unparseable files never change the exit code. `--check` continues to exit 1 only when files
would be re-arranged, and 0 otherwise.

sdsort is documented as a pre-commit hook and CI check. Because the dominant cause of a parse
failure is "this file uses syntax newer than the interpreter sdsort runs under", failing the run
would break the hook for anyone whose codebase targets a newer Python than their sdsort
environment. A formatter that cannot read a file should say so, not block the commit.

### Only parse and read errors are caught

Caught, and reported as warnings:

| Exception | Raised from | Covers |
| --- | --- | --- |
| `SyntaxError` | `ast.parse` | Invalid syntax, syntax newer than the running interpreter, indentation errors, and source containing null bytes (all surface as `SyntaxError` on Python 3.11) |
| `tokenize.TokenError` | `_should_skip` | Unterminated constructs the tokenizer rejects but `ast` accepts |
| `UnicodeDecodeError` | `read_file` | Files that are not valid UTF-8 |
| `OSError` | `read_file` | Permission denied, file removed mid-run |

Every other exception, `RecursionError` included, propagates and crashes the run.

Rationale: sdsort is beta. An internal defect that silently downgrades to a per-file warning
would leave files quietly unsorted, and the user would have no reason to report it. A crash is
the correct outcome for a bug in the tool itself.

Notes on the taxonomy:

- `IndentationError` and `TabError` are `SyntaxError` subclasses and need no separate handling.
- `tokenize.TokenError` derives directly from `Exception`, not `SyntaxError`, so it must be named
  explicitly.
- `UnicodeDecodeError` is caught by name rather than via its `ValueError` base, which would be far
  too broad.

### Warnings are grouped at the end, on stderr

A grouped section matches the existing structure of `_print_results`, which already emits one
section per category. It also keeps output deterministic now that files are sorted across worker
processes: streaming a warning at the moment of failure would interleave nondeterministically and
make CI log diffs noisy.

## Approach

Catch the error in the CLI worker function `_sort_file`, not in `step_down_sort`.

Two alternatives were considered and rejected:

- **Catch inside `step_down_sort`, adding an `"unparseable"` variant to `ResultType`.** This would
  give library consumers the same robustness, but it would stop `test/smoke_test.py` from seeing
  raised exceptions. That check is the project's main regression net against sdsort defects, and
  weakening it to gain robustness the CLI can provide on its own is a bad trade.
- **Catch in the parent process using per-future `submit()`.** Only necessary if the parent needed
  the exception object itself. It adds bookkeeping and gives up the ordering guarantee that
  `pool.map` provides, for no benefit.

## Detailed design

### `_sort_file`

Returns `(outcome, reason)` rather than a bare outcome string, where `reason` is `None` for every
outcome except the new `"unparseable"`. The reason is formatted inside the worker, so only `str`
crosses the process boundary and no exception object needs to be pickled.

`str(SyntaxError)` renders as `invalid syntax (<unknown>, line 1)`; the `<unknown>` filename is
noise, because the path is already shown alongside the message. The reason is therefore built from
`e.msg` and `e.lineno`:

```text
expected '(' (line 12)
```

For a `SyntaxError` with no `lineno`, the message alone is used. For the other caught exception
types, `str(e)` is used directly.

### `Results`

Gains `unparseable_files: list[tuple[str, str]]`, holding `(file_path, reason)` pairs.

`__len__` includes this bucket, so the `Checked N files` total continues to count every path that
was considered. Unparseable files are excluded from the `already sorted` count.

### Output

`_print_results` gains a section emitted with `click.secho(..., err=True)`:

```text
Re-arranged the following files:
- src/app.py

Could not parse the following files:
- src/new_syntax.py: expected '(' (line 12)
- src/latin1.py: 'utf-8' codec can't decode byte 0xe9 in position 4

2 files could not be parsed
410 files already sorted
Done! Checked 413 files in 0.31s
```

The counts are consistent: 1 re-arranged + 2 unparseable + 410 already sorted = the 413 reported
as checked.

The example shows stdout and stderr as a terminal interleaves them. All three pieces of warning
output — the `Could not parse the following files:` header, the file list, and the
`N files could not be parsed` count — go to stderr. Everything else keeps its current stream.
The header and the count use `fg="yellow"`, matching how the existing `skipped` section is
rendered.

## Testing

Unit tests in `test/test_sdsort.py`:

- A file containing invalid syntax produces a warning, exit code 0, and leaves the file untouched.
- A non-UTF-8 file produces a warning rather than a crash.
- A directory holding one broken file plus several sortable ones sorts every sortable file and
  still exits 0.
- `--check` over a directory whose only problem is an unparseable file exits 0.
- `--check` still exits 1 when a *sortable* file would be re-arranged, even alongside an
  unparseable one.
- The parallel path (`-j 4`) reports the same warnings as `-j 1`.

Corpus check: re-running all 1911 files under `test/repos/` must yield 74 warnings and zero
crashes, with the sorted output of the other 1837 files unchanged.

## Documentation

A short note under Usage in `README.md`: files sdsort cannot parse are reported and skipped, and
do not fail the run.
