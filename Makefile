PYTHON ?= $(shell mise which python 2>/dev/null || echo python3.14)
VENV := .venv
BIN := $(VENV)/bin

.PHONY: venv test clean

$(BIN)/pytest: requirements_test.txt
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -r requirements_test.txt
	touch $@

venv: $(BIN)/pytest

test: venv
	$(BIN)/pytest

clean:
	rm -rf $(VENV) .pytest_cache .coverage
