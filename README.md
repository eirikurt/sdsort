# sdsort
Sorts methods within python classes according to the step-down rule, as described in [Robert C. Martin's](https://en.wikipedia.org/wiki/Robert_C._Martin) [Clean Code](https://www.oreilly.com/library/view/clean-code-a/9780136083238/).
More concretely, methods are ordered in a depth-first-traversal order of the dependency tree.

## Installation
`pip install sdsort`

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
