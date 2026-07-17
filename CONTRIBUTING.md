# Contributing to sdsort

Thanks for your interest in contributing! Contributions of all kinds are
welcome — bug reports, new test cases, fixes, and features.

Before diving in, it helps to know what the tool does and how it works:

- [`README.md`](README.md) — what sdsort is and how to use it.
- [`CLAUDE.md`](CLAUDE.md) — a tour of the architecture and the sorting
  algorithm. Despite the name, it's a genuinely useful map of the codebase for
  any contributor.

## Getting set up

sdsort uses [uv](https://docs.astral.sh/uv/) for dependency management and
requires Python ≥3.11.

```bash
git clone https://github.com/eirikurt/sdsort.git
cd sdsort
uv sync
```

That's it — `uv sync` installs the project and all dev dependencies into a
local virtual environment.

## Development workflow

Everything runs through `make`. Before pushing, make sure the full check gate
passes:

```bash
make rpt          # Runs, in order: ruff → pyright → test
```

The individual steps are also available:

```bash
make test         # Run the pytest suite
make ruff         # Format code and sort imports
make pyright      # Type check
make testx        # Stop on first failure and drop into pdb (handy while debugging)
```

To run a single test case by name:

```bash
make case single_class
```

The name is matched via `pytest -k`, so it works for any test — a parametrized
case like `single_class` or a standalone test like `form_feed`.

## How tests work

This is the part most worth understanding before you contribute a change.

Most tests are **input/output file pairs** in `test/cases/`:

- `<name>.in.py` — source with functions/methods in some arbitrary order.
- `<name>.out.py` — the expected result after sorting.

The runner in `test/test_sdsort.py` feeds each `.in.py` file through
`step_down_sort()` and asserts the output matches the corresponding `.out.py`
file exactly.

### Adding a test case

Fixing a bug or adding a behavior almost always means adding a case:

1. Create `test/cases/<name>.in.py` with the input source.
2. Create `test/cases/<name>.out.py` with the expected sorted output.
3. Add `"<name>"` to the `test_all_cases` parametrize list in
   `test/test_sdsort.py`.
4. Run it: `make case <name>`.

Give the case a descriptive name — the existing cases (e.g.
`circular_functions`, `deferred_statement_annotation`,
`class_attribute_name_collision`) read like a catalogue of the behaviors the
tool handles, and that's intentional.

> **Tip:** A minimal `.in.py` / `.out.py` pair is also the ideal way to report
> a bug. It states the expected behavior precisely and drops straight into the
> suite.

## Code style

- **Formatting & imports:** handled by [ruff](https://docs.astral.sh/ruff/).
  Run `make ruff` before committing.
- **Type checking:** [pyright](https://microsoft.github.io/pyright/) in strict
  mode. `make pyright` must be clean.
- **Line length:** 115.

`test/cases/` is intentionally excluded from both ruff and pyright — those
files are fixtures and are meant to contain deliberately unsorted (and
sometimes unusual) code. Don't reformat them.

When in doubt, match the style of the surrounding code.

## Submitting changes

1. For anything larger than a small fix, consider
   [opening an issue](https://github.com/eirikurt/sdsort/issues) first to
   discuss the approach. It's encouraged, not required — small fixes and test
   cases are welcome as PRs directly.
2. Fork the repo and create a branch for your change.
3. Make sure `make rpt` passes.
4. Open a pull request against `main` with a clear description of what changed
   and why. If it relates to an issue, reference it.

Write clear, descriptive commit messages — there's no strict format required.

CI runs the test suite across Python 3.11–3.14 on Linux, plus a Windows run,
and enforces the same lint and type checks as `make rpt`. If `make rpt` passes
locally, CI should be green too.

## Reporting bugs

Open an issue at https://github.com/eirikurt/sdsort/issues. The most helpful
report includes a **minimal snippet that reproduces the problem** — ideally
framed as "here's the input, here's what I expected, here's what I got,"
since that maps directly onto a test case.
