SHELL := /bin/bash

.PHONY: test

black:
	poetry run black sdsort test

test:
	poetry run pytest test/