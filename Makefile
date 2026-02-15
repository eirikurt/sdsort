SHELL := /bin/bash

.PHONY: test

ruff:
	uv run ruff check --select I --fix
	uv run ruff format

pyright:
	uv run pyright

test:
	uv run pytest

rpt: ruff pyright test
