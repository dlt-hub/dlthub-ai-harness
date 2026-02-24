.PHONY: dev validate-toolkits

dev:
	uv sync

validate-toolkits:
	uv run python tools/validate_toolkits.py
