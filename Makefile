SHELL := /bin/bash

.PHONY: ruff pyright test testx case rpt

ruff:
	uv run ruff check --fix
	uv run ruff format

pyright:
	uv run pyright

test:
	uv run pytest

testx:
	uv run pytest -x --pdb -vv

# Run a single test case, e.g. `make case async_functions`
# The case name is taken as a positional argument (matched via pytest -k).
CASE := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
ifeq (case,$(firstword $(MAKECMDGOALS)))
ifneq ($(CASE),)
# Turn the trailing word(s) into no-op targets so make doesn't try to build them.
$(eval $(CASE):;@:)
endif
endif

case:
ifeq ($(strip $(CASE)),)
	$(error Usage: make case <test_case_name>)
endif
	uv run pytest -v -k "$(CASE)"

rpt: ruff pyright test
