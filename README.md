# sdsort

Sorts **top-level functions** and **class methods** in Python files according to the step-down rule, as described in [Robert C. Martin's](https://en.wikipedia.org/wiki/Robert_C._Martin) [Clean Code](https://www.oreilly.com/library/view/clean-code-a/9780136083238/).
More concretely, functions and methods are ordered in a depth-first-traversal order of the dependency tree, so higher-level code appears before the lower-level code it calls.

## Installation

`pip install sdsort`

Or run directly with [uv](https://docs.astral.sh/uv/):

`uvx sdsort <path>`

## Usage

To target individual files, run the `sdsort` command, followed by the paths to the files that should be sorted:
```
sdsort <file_1> <file_2>
```

To sort all `*.py` files in a directory, and all of its subdirectories, run the `sdsort` command followed by the directory path:
```
sdsort <directory_path>
```

## Maturity

It's early days. Consider this an alpha for now.
