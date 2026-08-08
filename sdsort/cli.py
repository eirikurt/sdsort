import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from glob import glob
from tokenize import TokenError
from typing import Iterable, Literal, Union

import click

from .sort import step_down_sort
from .utils.pluralize import pluralize
from .utils.timer import Timer

# TODO: switch to pathlib

# Spawning workers costs a few tens of milliseconds, which only pays for itself once there is a
# meaningful amount of work to spread across them.
_MIN_FILES_FOR_PARALLELISM = 50

# A ceiling on worker processes, independent of how it was requested (explicit -j or the CPU-count
# auto-detection below). Past this, the bookkeeping and IPC overhead of more workers stops paying
# for itself, and an accidental `-j 5000` should degrade gracefully rather than trying to spawn it.
_MAX_WORKERS = 64

# Only parse and read failures are tolerated. Anything else is a defect in sdsort itself, and a
# crash is the right outcome for that: a per-file warning would leave files quietly unsorted.
_UNPARSEABLE = (SyntaxError, TokenError, UnicodeDecodeError, OSError)

FileOutcome = Union[
    tuple[Literal["sorted", "skipped", "unchanged"], None],
    tuple[Literal["unparseable"], str],
]


@click.command()
@click.argument(
    "paths",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, readable=True),
    is_eager=True,
)
@click.option("--check", is_flag=True, help="Don't write changes, just report if files would be re-arranged.")
@click.option(
    "--jobs",
    "-j",
    type=click.IntRange(min=0),
    default=0,
    help=(
        "Number of parallel worker processes. 0 (the default) picks one per available CPU; 1 "
        f"disables parallelism. Runs of fewer than {_MIN_FILES_FOR_PARALLELISM} files always stay "
        "serial regardless of this setting, since spawning workers costs more than it saves at "
        "that scale."
    ),
)
def main(paths: tuple[str, ...], check: bool, jobs: int):
    file_paths = _expand_file_paths(paths)

    with Timer() as t:
        results = _sort_files(sorted(file_paths), check, jobs)

    _print_results(results, check, t.elapsed)

    if check and len(results.modified_files) > 0:
        raise SystemExit(1)


def _expand_file_paths(paths: tuple[str, ...]) -> Iterable[str]:
    file_paths = []
    for path in paths:
        if os.path.isdir(path):
            file_paths.extend(glob(os.path.join(path, "**/*.py"), recursive=True))
        else:
            file_paths.append(path)
    return file_paths


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


def _sort_each(file_paths: list[str], check: bool, jobs: int) -> list[FileOutcome]:
    """Sort every file, returning one outcome per input path, in input order."""
    sort_one = partial(_sort_file, check=check)
    workers = _worker_count(len(file_paths), jobs)
    if workers == 1:
        return [sort_one(file_path) for file_path in file_paths]

    # Sorting is ~98% CPU-bound, so only separate processes buy real parallelism. chunksize stays
    # at 1 because file sizes vary enough that batching them noticeably skews the load balance.
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(sort_one, file_paths, chunksize=1))


def _worker_count(file_count: int, jobs: int) -> int:
    if jobs == 0:
        if file_count < _MIN_FILES_FOR_PARALLELISM:
            return 1
        jobs = _available_cpu_count()
    return max(1, min(jobs, file_count, _MAX_WORKERS))


def _available_cpu_count() -> int:
    """Best-effort count of CPUs this process may actually use.

    os.cpu_count() reports the host's total core count, which overshoots badly when the process is
    confined by a container CPU quota or by scheduler affinity — the common case for sdsort, which
    is typically invoked from CI containers and pre-commit hooks rather than bare metal. Prefer, in
    order: process_cpu_count (3.13+, honours both quotas and affinity), sched_getaffinity (Linux
    only, honours affinity), then the unconstrained cpu_count as a last resort.
    """
    if sys.version_info >= (3, 13):
        return os.process_cpu_count() or 1
    if sys.platform != "win32" and sys.platform != "darwin":
        return len(os.sched_getaffinity(0))
    return os.cpu_count() or 1


def _describe_failure(error: Exception) -> str:
    """Render an exception's message for display next to the file path that caused it.

    str(SyntaxError) renders as "invalid syntax (broken.py, line 1)", repeating a file name that
    the caller already prints alongside the reason, so the message is rebuilt from its parts.
    str(OSError) has the same problem — e.g. "[Errno 13] Permission denied: './noread.py'" — so
    its strerror is used instead when the OS supplied one.
    """
    if isinstance(error, SyntaxError):
        message = error.msg or "invalid syntax"
        return f"{message} (line {error.lineno})" if error.lineno is not None else message
    if isinstance(error, OSError) and error.strerror is not None:
        return error.strerror
    return str(error)


def _sort_file(file_path: str, check: bool) -> FileOutcome:
    """Sort a single file, writing it back in place unless this is a --check run.

    This runs inside a worker process, so it writes the file itself rather than shipping the whole
    modified source back to the parent, and it renders the failure reason to a string here so that
    only picklable data crosses the process boundary.
    """
    try:
        modification = step_down_sort(file_path)
    except _UNPARSEABLE as error:
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


def _print_results(results: Results, check: bool, duration: float):
    if len(results.modified_files) > 0:
        if check:
            click.secho("The following files would be re-arranged:", fg="yellow", bold=True)
        else:
            click.secho("Re-arranged the following files:", fg="yellow", bold=True)
        for modified_file in results.modified_files:
            click.echo(f"- {modified_file}")
    if len(results.unparseable_files) > 0:
        click.secho("Could not parse the following files:", fg="yellow", bold=True, err=True)
        for unparseable_file, reason in results.unparseable_files:
            click.echo(f"- {unparseable_file}: {reason}", err=True)
        click.secho(
            f"{pluralize(len(results.unparseable_files), 'file')} could not be parsed",
            fg="yellow",
            err=True,
        )
    if len(results.skipped_files) > 0:
        click.secho(
            f"{pluralize(len(results.skipped_files), 'file')} skipped",
            fg="yellow",
        )
    if len(results.pristine_files) > 0:
        click.secho(
            f"{pluralize(len(results.pristine_files), 'file')} already sorted",
            fg="green",
        )

    if len(results) == 0:
        click.secho("No python files found to format", fg="yellow")
    else:
        click.secho(f"Done! Checked {pluralize(len(results), 'file')} in {duration:.2f}s", dim=True)
