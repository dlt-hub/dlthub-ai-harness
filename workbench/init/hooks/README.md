# Universal secrets-read guard

`secrets_guard.py` blocks direct reads of dlt secrets (`secrets.toml`, `*.secrets.toml`)
and dotenv files (`.env`, `.env.*` except `.env.example`/`.env.template`/`.env.sample`)
across **Claude Code, Codex, and Cursor** — one stdlib-only script, no imports, safe to
copy anywhere. See `docs/superpowers/specs/2026-07-01-secrets-read-hook-design.md` for
the full design.

## How one script serves three agents

The script detects the calling agent from the stdin payload and answers in that
agent's dialect:

| Agent | Detection | Input fields | Deny output |
|-------|-----------|--------------|-------------|
| Claude Code / Codex | `tool_name` present, `hook_event_name` not a Cursor event | `tool_input.file_path` / `.paths` / `.command` | `{"hookSpecificOutput": {"permissionDecision": "deny", ...}}` |
| Cursor | `hook_event_name` ∈ {`beforeReadFile`, `beforeShellExecution`} | top-level `file_path` / `command` | `{"permission": "deny", ...}` |

The discriminator is the `hook_event_name` **value**, not its presence — Claude also
sends `hook_event_name` (as `"PreToolUse"`), so only Cursor's event names route to the
Cursor dialect.

## Status per agent

| Config | Agent | Wired up? |
|--------|-------|-----------|
| `hooks.json` | Claude Code | **Yes** — auto-discovered when this plugin is installed via the Claude Code marketplace. |
| `codex-hooks.json` | Codex | Via `dlthub-init` (planned) — scaffolder copies the script and writes `.codex/hooks.json`. Note: `.codex/config.toml [hooks]` is avoided due to an open upstream bug (openai/codex#17532 — repo-local config.toml hooks don't fire in interactive sessions); `hooks.json` is confirmed working. |
| `cursor-hooks.json` | Cursor | Via `dlthub-init` (planned) — scaffolder copies the script and writes `.cursor/hooks.json`. |

The `codex-hooks.json` / `cursor-hooks.json` files here are templates: the `command`
paths reference the script by bare filename and must be adjusted to the actual install
location when wired up (neither agent exposes a `${CLAUDE_PLUGIN_ROOT}`-style variable).

## Manual testing

```bash
# Claude / Codex dialect (stdin: {tool_name, tool_input})
echo '{"tool_name":"Read","tool_input":{"file_path":".dlt/secrets.toml"}}' | python3 secrets_guard.py

# Cursor dialect (stdin: {hook_event_name, file_path|command})
echo '{"hook_event_name":"beforeShellExecution","command":"cat .env"}' | python3 secrets_guard.py

# Allowed reads produce no output (Claude/Codex) or {"permission": "allow"} (Cursor)
echo '{"tool_name":"Read","tool_input":{"file_path":".env.example"}}' | python3 secrets_guard.py
```
