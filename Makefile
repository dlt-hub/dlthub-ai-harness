.PHONY: dev dev-dlt-floor dev-dlt-prerelease validate-toolkits test lint lint-ruff lint-mypy format format-fix lint-install

# the lowest released dlt `pyproject.toml` claims to work against, read off the declaration so
# the version lives in one place
DLT_FLOOR = $(shell sed -n 's/.*"dlt\[hub\]>=\(.*\)",/\1/p' pyproject.toml)

# the prerelease dlt to test against, as a pip requirement. supplied by the environment and
# never committed: this repo is public and the archive it points at may not be
DLT_PRERELEASE ?=

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

# the dlt a release has not shipped yet. what it demands here is what the next release will
# demand. set `DLT_PRERELEASE` to the archive or the version, and the install is forced
# because an archive url carries no version for uv to compare
dev-dlt-prerelease: dev
	@test -n "$(DLT_PRERELEASE)" || { \
		echo "set DLT_PRERELEASE to the dlt requirement to test against"; exit 1; }
	uv pip install --reinstall-package dlt "$(DLT_PRERELEASE)"

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
