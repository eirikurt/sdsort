# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

sdsort is a Python CLI tool that sorts both **class methods** and **top-level functions** according to the "step-down rule" from Clean Code. Items are reordered in depth-first-traversal order of their dependency tree, so higher-level items appear before the lower-level items they call.

## Commands

```bash
make rpt          # Run all checks: ruff → pyright → test
make test         # Run pytest suite
make ruff         # Format and sort imports
make pyright      # Type check

# Run a single test case (matches by name via pytest -k)
make case single_class
```

## Architecture

The package is split across several modules in `sdsort/`:

- **`cli.py`** — Click entry point (`main()`). Handles `--check` flag, directory expansion, and output formatting.
- **`sort.py`** — Core logic (`step_down_sort()`). Orchestrates the two-pass sort: top-level blocks first, then methods within each class.
- **`block.py`** — `Block` hierarchy: `FunctionBlock`, `ClassBlock`, `StatementBlock`. Each knows its line range, how to find outgoing calls (`find_calls()`), and how to find predecessor constraints (`find_predecessors()`).
- **`context.py`** — `Context` dataclass. Detects `from __future__ import annotations` to decide whether type annotations should be evaluated as predecessors.
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

Tests use input/output file pairs in `test/cases/`:
- `*.in.py` - Input source with methods in arbitrary order
- `*.out.py` - Expected output after sorting

The test runner compares `step_down_sort()` output against the `.out.py` content.

## Configuration

- Python ≥3.11, line length 115, strict type checking
- `test/cases/` is excluded from ruff and pyright (intentional test fixtures)
