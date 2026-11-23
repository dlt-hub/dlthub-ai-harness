.PHONY: dev validate-toolkits test lint lint-ruff lint-mypy format format-fix lint-install codex-zip

# an install copies an agent folder verbatim, so bytecode written beside a shipped module
# travels into every workspace
export PYTHONDONTWRITEBYTECODE = 1

dev:
	uv sync --group lint --group test --reinstall-package dlt

validate-toolkits:
	uv run python tools/validate_toolkits.py

test:
	uv run --group test pytest tests

lint-ruff:
	uv run ruff check tools
	uv run ruff format --check tools

lint-mypy:
	uv run mypy tools --no-namespace-packages

format:
	uv run ruff format tools

format-fix: format
	uv run ruff check --fix tools

lint-install:
	uv run python tools/lint_install.py

lint: lint-ruff lint-mypy validate-toolkits lint-install test

# the Codex directory takes a ZIP upload of the launcher plugin folder
CODEX_ZIP = dist/dlthub-setup-codex.zip

codex-zip:
	uv run python tools/generate_catalogs.py --check
	rm -f $(CODEX_ZIP) && mkdir -p dist
	cd workbench/dlthub-setup && zip -rqX ../../$(CODEX_ZIP) .codex-plugin skills assets LICENSE README.md -x '*.DS_Store'
	@echo "Wrote $(CODEX_ZIP)"
