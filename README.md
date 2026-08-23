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

### Method order

Within a class, methods are sorted by call order — the step-down rule — unless told otherwise. Methods can also be grouped by visibility, or ordered alphabetically, via a `[tool.sdsort]` table in the `pyproject.toml` file nearest to the file being sorted (the closest one at or above it in the directory tree):

```toml
[tool.sdsort]
method-order = ["visibility", "call", "name"]
```

`method-order` lists the attributes to sort by, most significant first. The example above groups methods by visibility, orders each group by call order, and falls back to alphabetical order for methods no call relationship ranks. The available attributes are:

- `call` — the step-down rule: a method appears before the methods it calls.
- `visibility` — grouped by visibility, in the order given by `visibility-order` (see below).
- `name` — alphabetically by method name.

The default is `["call"]`. Only methods within classes are affected; top-level functions are always sorted by call order.

### Visibility order

A method's visibility is determined by its name:

| Visibility  | Name                                        | Example    |
| ----------- | ------------------------------------------- | ---------- |
| `dunder`    | leading and trailing double underscore      | `__init__` |
| `private`   | leading double underscore                   | `__cache`  |
| `protected` | single leading underscore                   | `_helper`  |
| `public`    | no leading underscore                       | `run`      |

`visibility-order` lists the visibilities in the order their groups should appear:

```toml
[tool.sdsort]
method-order = ["visibility", "call"]
visibility-order = ["dunder", "public", "protected", "private"]
```

That is also the default. Any visibility left out of the list is placed last, keeping whatever order the remaining `method-order` attributes give it. To place the omitted ones somewhere else, name their position with `"*"`:

```toml
visibility-order = ["dunder", "*", "private"]
```

Dunder methods come first and private methods last, with everything else in between. `visibility-order` has no effect unless `"visibility"` appears in `method-order`.

### Invalid configuration

If a `[tool.sdsort]` table holds something sdsort cannot honour — an unknown key or value, a duplicate, a value that is not a list — sdsort reports every problem it found and exits with code 1.

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
