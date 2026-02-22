.PHONY: dev validate-plugins

dev:
	uv sync

validate-plugins:
	uv run python tools/validate_plugins.py
