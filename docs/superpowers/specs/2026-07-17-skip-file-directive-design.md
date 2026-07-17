# Design: `# sdsort: skip_file` directive

Resolves [#37](https://github.com/eirikurt/sdsort/issues/37).

## Goal

Let authors exempt an individual file from sorting by placing a comment
directive in it, avoiding the need for configurable include/exclude glob
patterns in `pyproject.toml`.

## Directive

- Spelling: `# sdsort: skip_file`
- Namespaced after isort's `# isort: skip_file` so finer-grained directives
  (e.g. `skip`, `split`, on/off regions) can be added later without ambiguity.
- Recognized **anywhere in the file**, as long as it is a genuine comment.
- Matching is tolerant of surrounding whitespace but case-sensitive on the
  `sdsort` / `skip_file` tokens: `^#\s*sdsort:\s*skip_file\s*$`.
- A trailing comment (`x = 1  # sdsort: skip_file`) counts, consistent with the
  "anywhere in the file" rule.

## Detection — `sdsort/directive.py`

New module with a single function:

```python
def is_file_skipped(source: str) -> bool
```

It tokenizes `source` with `tokenize.generate_tokens` and returns `True` if any
`COMMENT` token matches the directive pattern. Using the tokenizer (rather than
a line-based regex over the raw text) means a `# sdsort: skip_file` string that
appears inside a docstring or other literal does **not** falsely trigger a skip.
This matches the tokenizer-accurate handling used elsewhere in the project
(e.g. `split_lines`, the form-feed handling).

If tokenizing raises (malformed source), `is_file_skipped` returns `False` so
the file falls through to the normal sort path, which surfaces the syntax error
the same way it does today.

## Read the file once

`step_down_sort` currently reads the file itself. To avoid reading each file
twice (once to check the directive, once to sort), thread the already-read
source through an optional parameter:

```python
def step_down_sort(python_file_path: str | Path, source: str | None = None) -> Optional[str]:
    if source is None:
        source = read_file(python_file_path)
    ...
```

Existing callers that pass only a path (the tests) keep working and read once as
before. The CLI reads once and passes the source in.

## CLI gate — `sdsort/cli.py`

`_sort_files` reads each file's source once, then decides:

```python
for file_path in file_paths:
    source = read_file(file_path)
    if is_file_skipped(source):
        results.skipped_files.append(file_path)
        continue
    modified_source = step_down_sort(file_path, source)
    ...
```

Skipped files never reach `step_down_sort`, so they can never be reported as
"would be re-arranged".

## Reporting — `Results` and `_print_results`

- `Results` gains `skipped_files: list[str]` (default empty).
- `Results.__len__` includes skipped files in the total count.
- `_print_results` prints a line for skipped files when any exist, e.g.
  `N files skipped (# sdsort: skip_file)`.
- Because skipped files are not in `modified_files`, a `--check` run over
  skipped-only input exits `0`.

## Testing

Fixture-based `.in.py` / `.out.py` cases don't fit "unchanged" behavior, so use
direct and CLI tests in the style of the existing non-fixture tests:

Unit tests for `is_file_skipped`:
- standalone comment line → `True`
- trailing comment on a code line → `True`
- extra internal whitespace (`#   sdsort:   skip_file`) → `True`
- directive text inside a string literal / docstring → `False`
- absent → `False`
- unrelated comment (`# sdsort rocks`) → `False`

CLI / integration tests:
- A file containing the directive is left byte-for-byte unchanged and is
  reported as skipped.
- `--check` over a directive'd (otherwise-unsorted) file exits `0`.
- `step_down_sort(path)` still works when called with only a path.

## Documentation

Add a short section to `README.md` describing the directive and its file-wide
effect.

## Out of scope

- Finer-grained directives (single-definition skip, on/off regions).
- `pyproject.toml` include/exclude glob configuration.
