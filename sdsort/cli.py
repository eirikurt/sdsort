import os
from dataclasses import dataclass, field
from glob import glob
from typing import Iterable

import click

from .sort import step_down_sort
from .utils.pluralize import pluralize
from .utils.timer import Timer

# TODO: switch to pathlib


@click.command()
@click.argument(
    "paths",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, readable=True),
    is_eager=True,
)
@click.option("--check", is_flag=True, help="Don't write changes, just report if files would be re-arranged.")
def main(paths: tuple[str, ...], check: bool):
    file_paths = _expand_file_paths(paths)

    with Timer() as t:
        results = _sort_files(sorted(file_paths), check)

    _print_results(results, check, t.elapsed)

    if check and len(results.modified_files) > 0:
        raise SystemExit(1)


@dataclass
class Results:
    modified_files: list[str] = field(default_factory=list)
    pristine_files: list[str] = field(default_factory=list)

    def __len__(self):
        return len(self.modified_files) + len(self.pristine_files)


def _sort_files(file_paths: list[str], check: bool):
    results = Results()

    for file_path in file_paths:
        modified_source = step_down_sort(file_path)
        if modified_source is not None:
            if not check:
                with open(file_path, "w") as file:
                    file.write(modified_source)
            results.modified_files.append(file_path)
        else:
            results.pristine_files.append(file_path)

    return results


def _print_results(results: Results, check: bool, duration: float):
    if len(results.modified_files) > 0:
        if check:
            click.secho("The following files would be re-arranged:", fg="yellow", bold=True)
        else:
            click.secho("Re-arranged the following files:", fg="yellow", bold=True)
        for modified_file in results.modified_files:
            click.echo(f"- {modified_file}")
    if len(results.pristine_files) > 0:
        click.secho(
            f"{pluralize(len(results.pristine_files), 'file')} left unchanged",
            fg="green",
        )

    if len(results) == 0:
        click.secho("No python files found to format", fg="yellow")
    else:
        click.secho(f"Done! Checked {pluralize(len(results), 'file')} in {duration:.2f}s", dim=True)


def _expand_file_paths(paths: tuple[str, ...]) -> Iterable[str]:
    file_paths = []
    for path in paths:
        if os.path.isdir(path):
            file_paths.extend(glob(os.path.join(path, "**/*.py"), recursive=True))
        else:
            file_paths.append(path)
    return file_paths
