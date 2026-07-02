"""Shared blocklist logic for the secrets-read PreToolUse hooks.

Imported by both block_secrets_access.py (Claude/Codex) and
cursor_block_secrets_access.py (Cursor) so the pattern list lives in one place.
"""

import os
import shlex

_ALLOWED_ENV_SUFFIXES = {"example", "template", "sample"}

DENY_MESSAGE = (
    "Blocked: direct access to secrets/env files is not allowed. "
    "Use the dlt-workspace-mcp `secrets_view_redacted` tool to inspect values (redacted) "
    "or `secrets_update_fragment` to write placeholders. See the setup-secrets skill."
)


def is_blocked_path(path: str) -> bool:
    """True if the basename of `path` looks like a dlt secrets or dotenv file."""
    name = os.path.basename(path.replace("\\", "/"))

    if name == "secrets.toml":
        return True
    if name.endswith(".secrets.toml"):
        return True

    if name == ".env":
        return True
    if name.startswith(".env."):
        suffix = name.rsplit(".", 1)[-1]
        return suffix not in _ALLOWED_ENV_SUFFIXES

    return False


def command_is_blocked(command: str) -> bool:
    """True if any token in a shell command string looks like a blocked path."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    return any(is_blocked_path(token) for token in tokens)
