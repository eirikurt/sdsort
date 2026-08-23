# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

sdsort is a Python CLI tool that sorts both **class methods** and **top-level functions** according to the "step-down rule" from Clean Code. Items are reordered in depth-first-traversal order of their dependency tree, so higher-level items appear before the lower-level items they call.

## Commands

```bash
make rtt          # Run all checks: ruff → typecheck → test
make test         # Run pytest suite
make ruff         # Format and sort imports
make typecheck    # Type check

# Run a single test case (matches by name via pytest -k)
make case single_class
```

## Architecture

The package is split across several modules in `sdsort/`:

- **`cli.py`** — Click entry point (`main()`). Handles `--check` flag, directory expansion, and output formatting.
- **`sort.py`** — Core logic (`step_down_sort()`). Orchestrates the two-pass sort: top-level blocks first, then methods within each class.
- **`block.py`** — `Block` hierarchy: `FunctionBlock`, `ClassBlock`, `StatementBlock`. Each knows its line range, how to find outgoing calls (`find_calls()`), and how to find predecessor constraints (`find_predecessors()`).
- **`context.py`** — `Context` dataclass and `gather_context()`. Combines the two facts a sort needs about a file: whether annotations are deferred (`from __future__ import annotations`, or a `requires-python` that rules out eager evaluation) and which `Config` applies.
- **`pyproject.py`** — `PyProject`. Encapsulates one pyproject.toml: `nearest_to()` finds the file governing a source path, `config` and `targets_python314_or_newer` read what sdsort needs out of it. Parsing is cached per path, so a project's file is read once per run.
- **`config.py`** — `Config` (the `[tool.sdsort]` table: `method-order`, `visibility-order`) and `ConfigError`. `from_toml()` validates the table and refuses anything it cannot honour — unknown keys or values, non-list values, duplicates — reporting every problem at once. `cli.py` catches `ConfigError` and exits 1 without rewriting a single file.
- **`graph.py`** — `AcyclicGraph`. Stores directed edges between blocks; silently drops edges that would create cycles.
- **`format.py`** — `normalize_blank_lines()`. Re-parses the rearranged source and enforces PEP 8 spacing (2 blanks before top-level defs, 1 between methods).
- **`utils/`** — `ast.py` (AST helpers including `determine_line_range()`), `file.py`, `pluralize.py`, `timer.py`.

### Algorithm

1. Parse source with `ast.parse()`.
2. Gather `Context` (detects deferred annotations).
3. Build `Block` objects for each top-level node. Non-function/class statements merge into `StatementBlock`s which act as "barriers" — any name they reference must be defined before them.
4. Build a dependency graph: edges from callers to callees (direct `func()` calls at top level; `self.method()` calls inside classes). Type annotations on function signatures are also treated as predecessor constraints (unless annotations are deferred via `__future__`).
5. Depth-first sort: visit each block and recursively pull its dependencies after it.
6. Rearrange source lines, then re-parse and sort methods within each class using the same algorithm with `self.method()` calls.
7. Normalize blank lines with `normalize_blank_lines()`.

`determine_line_range()` in `utils/ast.py` probes beyond AST-reported end lines to capture trailing content (multiline strings, comments) that belongs to a function/method.

## Test Structure

Tests use input/output file pairs under `test/cases/`, in a two-level layout:

```
test/cases/<configuration>/
    pyproject.toml    # the configuration under test
    <case>.in.py      # input source, items in arbitrary order
    <case>.out.py     # expected output after sorting
```

Each subdirectory is one configuration, holding one or more case pairs that exercise it.
`test/cases/default/` holds the cases that run against sdsort's defaults; its
`pyproject.toml` is deliberately empty so those cases resolve their configuration there
rather than from the repository root.

Directory names are derived from the configuration, not chosen: `method-order` as the
initials of its attributes, then `visibility-order` abbreviated after a double underscore
(`v_d_n__dun_pub_priv_prot`), stopping at the method order when `"visibility"` is absent
from it (`d_n`). `encode_configuration()` derives the name and discovery asserts every
directory matches it, so a directory cannot claim a configuration it does not hold and no
two can hold the same one. Case names describe only the case, since the directory already
carries the configuration.

`test_cases` discovers the pairs by scanning, so a new case is added by dropping a file
pair in (or a new subdirectory with its own `pyproject.toml`) — no test code to touch. It
compares `step_down_sort()` output against the `.out.py` content, and requires a case whose
input already matches its expected output to be reported as `unchanged`/`skipped` rather
than rewritten. A case needing a newer Python than the project floor is gated by an entry
in `MINIMUM_PYTHON_VERSIONS`.

## Configuration

- Python ≥3.11, line length 115, strict type checking
- `test/cases/` is excluded from ruff and basedpyright (intentional test fixtures)
