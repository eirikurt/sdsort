SHELL := /bin/bash

.PHONY: test

isort:
	poetry run isort sdsort test

black:
	poetry run black sdsort test --exclude ".*/test/cases/.*.py"

lint:
	poetry run flake8 sdsort test

mypy:
	poetry run mypy --show-error-codes sdsort/ test/

test:
	poetry run pytest test/

iblmt: isort black lint mypy test
