.PHONY: dev dev-dlt-floor dev-dlt-prerelease validate-toolkits test lint lint-ruff lint-mypy format format-fix lint-install

# the lowest released dlt `pyproject.toml` claims to work against, read off the declaration so
# the version lives in one place
DLT_FLOOR = $(shell sed -n 's/.*"dlt\[hub\]>=\(.*\)",/\1/p' pyproject.toml)

# the archive of the dlt a release has not shipped yet. supplied by the environment and never
# committed: this repository is public and the archive it points at may not be. locally it
# goes in `.env.local`, which git ignores; in CI it is an Actions secret, so the url stays out
# of a public build log
-include .env.local
DLT_PRERELEASE_URL ?=

# an install copies an agent folder verbatim, so bytecode written beside a shipped module
# travels into every workspace
export PYTHONDONTWRITEBYTECODE = 1

dev:
	uv sync --group lint --group test

# an agent definition names an entity type and a tool group out of dlt's own vocabulary, so a
# toolkit that only validates against the resolved dlt ships broken to whoever installs the
# floor. run the validator against it: `UV_NO_SYNC=1 make validate-toolkits test`, since a
# plain `uv run` re-syncs to the lock and undoes the pin.
dev-dlt-floor: dev
	uv pip install "dlt[hub]==$(DLT_FLOOR)"

# what the prerelease demands here is what the next release will demand. the install is forced
# because an archive url carries no version for uv to compare
dev-dlt-prerelease: dev
	@test -n "$(DLT_PRERELEASE_URL)" || { \
		echo "set DLT_PRERELEASE_URL to the dlt archive to test against"; exit 1; }
	uv pip install --reinstall-package dlt "dlt[hub] @ $(DLT_PRERELEASE_URL)"

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
