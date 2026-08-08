# sdsort

Sorts **top-level functions** and **class methods** in Python files according to the step-down rule, as described in [Robert C. Martin's](https://en.wikipedia.org/wiki/Robert_C._Martin) [Clean Code](https://www.oreilly.com/library/view/clean-code-a/9780136083238/).
More concretely, functions and methods are ordered in a depth-first-traversal order of the dependency tree, so higher-level code appears before lower-level code.

## Installation

`pip install sdsort`

Or run directly with [uv](https://docs.astral.sh/uv/):

`uvx sdsort <path>`

## Usage

To target individual files, run the `sdsort` command, followed by the paths to the files that should be sorted:

```bash
sdsort <file_1> <file_2>
```

To sort all `*.py` files in a directory, and all of its subdirectories, run the `sdsort` command followed by the directory path:

```bash
sdsort <directory_path>
```

To check if files are already sorted without modifying them, use the `--check` flag:

```bash
sdsort --check <file_or_directory>
```

This will exit with code 1 if any files would be re-arranged, making it suitable for CI pipelines and pre-commit hooks.

### Parallelism

Larger runs are sorted across parallel worker processes. Use `--jobs`/`-j` to control how many:

```bash
sdsort --jobs 4 <directory_path>
```

0 (the default) picks one worker per available CPU; 1 disables parallelism and sorts every file in the current process. Runs of fewer than 50 files always stay serial regardless of this setting, since spawning workers costs more than it saves at that scale.

### Files that cannot be parsed

If sdsort cannot parse a file, it reports the file on stderr and moves on. The rest of the files are still sorted, and the exit code is unaffected.

## Configuration

### Skipping a file

To prevent sdsort from modifying a particular file, add a `# sdsort: skip_file` comment somewhere within the file.

## pre-commit

`sdsort` can be used as a [pre-commit](https://pre-commit.com/) hook. Add the following to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/eirikurt/sdsort
    rev: v1.2.0
    hooks:
      - id: sdsort
```

## Maturity

It's early days. Consider this a beta for now.
