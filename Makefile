SHELL := /bin/bash

.PHONY: test

ruff:
	uv run ruff check --select I --fix
	uv run ruff format

pyright:
	uv run pyright

test:
	uv run pytest

testx:
	uv run pytest -x --pdb -vv

rpt: ruff pyright test
