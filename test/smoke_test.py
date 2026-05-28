#!/usr/bin/env python3
"""
Smoke-test sdsort against real-world Python repos.

Clones repos into test/repos/, then for each .py file verifies:
  1. sdsort doesn't raise an exception
  2. Output parses as valid Python
  3. Same set of top-level definition names (no code dropped or duplicated)
  4. No new ruff errors introduced (counts per error code must not increase)

Usage:
    uv run python test/smoke_test.py --clone   # first run: clone repos
    uv run python test/smoke_test.py           # subsequent runs
    uv run python test/smoke_test.py --repo name=https://github.com/org/repo
"""

import argparse
import ast
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sdsort import step_down_sort

ROOT = Path(__file__).parent.parent
REPOS_DIR = Path(__file__).parent / "repos"

sys.path.insert(0, str(ROOT))

DEFAULT_REPOS: list[tuple[str, str]] = [
    ("flask", "https://github.com/pallets/flask"),
    ("requests", "https://github.com/psf/requests"),
    ("black", "https://github.com/psf/black"),
]


@dataclass
class Failure:
    path: Path
    reason: str
    detail: str = ""

    def __str__(self) -> str:
        rel = self.path.relative_to(REPOS_DIR)
        msg = f"  FAIL {rel}: {self.reason}"
        if self.detail:
            msg += f"\n       {self.detail}"
        return msg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clone", action="store_true", help="Clone repos into test/repos/ before running")
    parser.add_argument("--repo", metavar="NAME=URL", action="append", default=[], help="Extra repo to include")
    args = parser.parse_args()

    repos = list(DEFAULT_REPOS)
    for r in args.repo:
        name, _, url = r.partition("=")
        repos.append((name.strip(), url.strip()))

    if args.clone:
        print("Cloning repos...")
        clone_repos(repos)

    sys.exit(run(repos))


def clone_repos(repos: list[tuple[str, str]]) -> None:
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in repos:
        dest = REPOS_DIR / name
        if dest.exists():
            print(f"  {name}: already present, skipping")
        else:
            print(f"  {name}: cloning {url} ...")
            subprocess.run(["git", "clone", "--depth=1", url, str(dest)], check=True)


def run(repos: list[tuple[str, str]]) -> int:
    total_files = total_changed = total_failed = 0

    for name, _ in repos:
        repo_dir = REPOS_DIR / name
        if not repo_dir.exists():
            print(f"\n{name}: not found in {REPOS_DIR} — run with --clone first")
            continue

        py_files = list(iter_py_files(repo_dir))
        print(f"\n{name}: {len(py_files)} files", flush=True)

        repo_failures: list[Failure] = []
        repo_changed = 0
        for py_file in py_files:
            total_files += 1
            changed, failures = check_file(py_file)
            if changed:
                repo_changed += 1
                total_changed += 1
            if failures:
                total_failed += 1
                repo_failures.extend(failures)

        if repo_failures:
            for f in repo_failures:
                print(str(f))
        print(f"  {repo_changed}/{len(py_files)} files reordered, {len(repo_failures)} failure(s)")

    print(f"\n{'─' * 60}")
    print(f"files checked: {total_files}   reordered: {total_changed}   failures: {total_failed}")
    return 1 if total_failed else 0


def iter_py_files(repo_dir: Path) -> Iterator[Path]:
    yield from sorted(repo_dir.rglob("*.py"))


def check_file(py_file: Path) -> tuple[bool, list[Failure]]:
    """Return (was_changed, failures). was_changed=True means sdsort actually reordered something."""
    try:
        original = py_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, []

    try:
        orig_tree = ast.parse(original, filename=str(py_file))
    except SyntaxError:
        return False, []  # skip files that are already broken

    try:
        sorted_source = step_down_sort(py_file)
    except Exception as exc:
        return False, [Failure(py_file, "raised exception", str(exc))]

    if sorted_source is None:
        return False, []  # unchanged

    failures: list[Failure] = []

    try:
        sorted_tree = ast.parse(sorted_source, filename=str(py_file))
    except SyntaxError as exc:
        return True, [Failure(py_file, "output is not valid Python", str(exc))]

    orig_names = top_level_names(orig_tree)
    sorted_names = top_level_names(sorted_tree)
    if orig_names != sorted_names:
        dropped = orig_names - sorted_names
        added = sorted_names - orig_names
        failures.append(Failure(py_file, "top-level names changed", f"dropped={dropped} added={added}"))

    orig_counts = ruff_error_counts(original, str(py_file))
    sorted_counts = ruff_error_counts(sorted_source, str(py_file))
    new_errors = {code: count for code, count in sorted_counts.items() if count > orig_counts.get(code, 0)}
    if new_errors:
        failures.append(Failure(py_file, "new ruff errors", str(new_errors)))

    return True, failures


def top_level_names(tree: ast.Module) -> set[str]:
    return {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


def ruff_error_counts(source: str, filename: str) -> dict[str, int]:
    result = subprocess.run(
        ["ruff", "check", "--isolated", "--select=E,F,W", "--stdin-filename", filename, "-"],
        input=source,
        capture_output=True,
        text=True,
    )
    counts: dict[str, int] = {}
    for line in result.stdout.splitlines():
        if m := re.search(r"\b([A-Z]\d+)\b", line):
            code = m.group(1)
            counts[code] = counts.get(code, 0) + 1
    return counts


if __name__ == "__main__":
    main()
