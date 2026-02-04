SHELL := /bin/bash

.PHONY: test

ruff:
	poetry run ruff check --select I --fix
	poetry run ruff format

pyright:
	poetry run pyright

test:
	poetry run pytest test/

rpt: ruff pyright test
