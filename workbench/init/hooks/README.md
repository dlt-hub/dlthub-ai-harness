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

## Delivery channels

- **Claude Code marketplace** — `hooks.json` here is auto-discovered when the `init`
  plugin is installed. Claude-only.
- **`dlthub-init` scaffolder** ([dlt-hub/dlthub-init](https://github.com/dlt-hub/dlthub-init))
  — syncs this script into its wheel and, at scaffold time, copies it to
  `.agents/hooks/` and registers it for all three agents (`.claude/settings.json`,
  `.cursor/hooks.json`, `.codex/hooks.json`). The per-agent config shapes are generated
  by its `hooks.py` — this directory intentionally ships no Cursor/Codex config
  templates to avoid drift. Codex note: configs go in `.codex/hooks.json`, not
  `.codex/config.toml [hooks]` (openai/codex#17532 — repo-local config.toml hooks
  don't fire in interactive sessions).

**Both channels at once:** a project scaffolded by `dlthub-init` that also installs the
`init` plugin from the marketplace registers the guard twice for Claude (plugin hook +
project settings hook). It then runs twice per tool call — harmless (same deny message,
allows are silent) but expected.

## Manual testing

```bash
# Claude / Codex dialect (stdin: {tool_name, tool_input})
echo '{"tool_name":"Read","tool_input":{"file_path":".dlt/secrets.toml"}}' | python3 secrets_guard.py

# Cursor dialect (stdin: {hook_event_name, file_path|command})
echo '{"hook_event_name":"beforeShellExecution","command":"cat .env"}' | python3 secrets_guard.py

# Allowed reads produce no output (Claude/Codex) or {"permission": "allow"} (Cursor)
echo '{"tool_name":"Read","tool_input":{"file_path":".env.example"}}' | python3 secrets_guard.py
```
