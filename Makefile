.PHONY: dev validate-toolkits lint lint-ruff lint-mypy format format-fix lint-install

dev:
	uv sync --group lint --reinstall-package dlt

validate-toolkits:
	uv run python tools/validate_toolkits.py

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

lint: lint-ruff lint-mypy validate-toolkits lint-install
