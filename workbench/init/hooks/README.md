# Secrets-read PreToolUse hook

Blocks direct reads of dlt secrets (`secrets.toml`, `*.secrets.toml`) and dotenv files
(`.env`, `.env.*` except `.env.example`/`.env.template`/`.env.sample`). See
`docs/superpowers/specs/2026-07-01-secrets-read-hook-design.md` for the full design.

## Status per agent

| File | Agent | Wired up? |
|------|-------|-----------|
| `hooks.json` + `block_secrets_access.py` | Claude Code | **Yes** — auto-discovered when this plugin is installed via the Claude Code marketplace. |
| `codex-hooks.json` + `block_secrets_access.py` | Codex | No — Codex installs go through the separate `dlthub ai` CLI, which has no `hook` component type yet. Content is ready; not copied anywhere automatically. |
| `cursor-hooks.json` + `cursor_block_secrets_access.py` | Cursor | Same as Codex — not wired up by the `dlthub ai` CLI yet. |

`_secrets_patterns.py` holds the shared blocklist logic used by both entrypoint scripts.

## Path assumption for the not-yet-wired configs

`codex-hooks.json` and `cursor-hooks.json` reference their scripts by **bare filename**
(e.g. `python3 block_secrets_access.py`), assuming the hook config and the script end up
in the same directory — mirroring how they sit in this repo. Neither Codex nor Cursor
expose a `${CLAUDE_PLUGIN_ROOT}`-style variable, so an absolute path can't be written
correctly until the real install location is known. Whoever wires up CLI support for
these two should adjust the `command` path to match wherever the script actually lands.

## Manual testing

```bash
# Claude / Codex schema (stdin: {tool_name, tool_input})
echo '{"tool_name":"Read","tool_input":{"file_path":".dlt/secrets.toml"}}' | python3 block_secrets_access.py

# Cursor schema (stdin: {hook_event_name, file_path|command})
echo '{"hook_event_name":"beforeShellExecution","command":"cat .env"}' | python3 cursor_block_secrets_access.py
```
