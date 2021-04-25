SHELL := /bin/bash

.PHONY: test

black:
	poetry run black sdsort test --exclude ".*/test/cases/.*.py"

test:
	poetry run pytest test/