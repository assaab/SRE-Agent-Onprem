PYTHON ?= python

.PHONY: lint test typecheck replay

lint:
	ruff check .

test:
	pytest

typecheck:
	mypy libs services agents adapters eval

replay:
	$(PYTHON) eval/replay/replay_runner.py
