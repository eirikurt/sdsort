import os
import time
from glob import glob
from typing import Iterable

import click

from .sorting import step_down_sort


@click.command()
@click.argument(
    "paths",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, readable=True),
    is_eager=True,
)
@click.option("--check", is_flag=True, help="Don't write changes, just report if files would be re-arranged.")
def main(paths: tuple[str, ...], check: bool):
    start_time = time.monotonic()
    file_paths = _expand_file_paths(paths)
    modified_files: list[str] = []
    pristine_files: list[str] = []

    for file_path in sorted(file_paths):
        modified_source = step_down_sort(file_path)
        if modified_source is not None:
            if not check:
                with open(file_path, "w") as file:
                    file.write(modified_source)
            modified_files.append(file_path)
        else:
            pristine_files.append(file_path)

    if len(modified_files) > 0:
        if check:
            click.secho("The following files would be re-arranged:", fg="yellow", bold=True)
        else:
            click.secho("Re-arranged the following files:", fg="yellow", bold=True)
        for modified_file in modified_files:
            click.echo(f"- {modified_file}")
    if len(pristine_files) > 0:
        click.secho(
            f"{len(pristine_files)} file{'' if len(pristine_files) == 1 else 's'} left unchanged", fg="green"
        )
    if len(modified_files) == 0 and len(pristine_files) == 0:
        click.secho("No python files found to format", fg="green")

    elapsed = time.monotonic() - start_time
    total_files = len(modified_files) + len(pristine_files)
    click.secho(f"Done! Checked {total_files} file{'' if total_files == 1 else 's'} in {elapsed:.2f}s", dim=True)

    if check and len(modified_files) > 0:
        raise SystemExit(1)


def _expand_file_paths(paths: tuple[str, ...]) -> Iterable[str]:
    file_paths = []
    for path in paths:
        if os.path.isdir(path):
            file_paths.extend(glob(os.path.join(path, "**/*.py"), recursive=True))
        else:
            file_paths.append(path)
    return file_paths
