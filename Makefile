PYTHON ?= $(shell mise which python 2>/dev/null || echo python3.14)
VENV := .venv
BIN := $(VENV)/bin

.PHONY: venv test clean release

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

# Usage: make release VERSION=0.3.0
# Needs a "## [VERSION]" section in CHANGELOG.md. Bumps the manifest, commits, tags and
# pushes; the Release workflow then publishes the GitHub release that HACS offers as update.
MANIFEST := custom_components/oven_control/manifest.json

release: test
	@test -n "$(VERSION)" || (echo "VERSION is required, e.g. make release VERSION=0.3.0" && exit 1)
	@grep -q '^## \[$(VERSION)\]' CHANGELOG.md || (echo "CHANGELOG.md has no section for $(VERSION)" && exit 1)
	@git diff --quiet HEAD -- . ':!CHANGELOG.md' || (echo "Commit other changes first" && exit 1)
	sed -i 's/"version": "[^"]*"/"version": "$(VERSION)"/' $(MANIFEST)
	git add $(MANIFEST) CHANGELOG.md
	git commit -m "chore: release $(VERSION)"
	git tag -a v$(VERSION) -m "v$(VERSION)"
	git push origin HEAD v$(VERSION)
