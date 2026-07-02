# PreToolUse hook to block direct secrets/env reads

## Problem

`setup-secrets` already documents a policy: "Never read secrets files directly — use `dlt-workspace-mcp` tools or `dlthub ai secrets` CLI commands." This is prompt-level only — nothing stops an agent from running `cat .dlt/secrets.toml`, `Read(".env")`, or `Grep` over a secrets file and leaking real values into the transcript. We want a technical enforcement layer, not just an instruction, across all three supported agents: Claude Code, Cursor, Codex.

## Scope

Build the hook **content** (scripts + per-agent config) for all three agents now. Auto-installation differs per agent:

- **Claude Code**: plugins auto-discover `hooks/hooks.json` at the plugin root and load it on install (via marketplace / `/plugin`). This works today, no CLI changes needed.
- **Cursor / Codex**: these agents don't consume this repo's `.claude-plugin/marketplace.json` at all — installation for them normally goes through the separate `dlthub ai` CLI, which copies toolkit content into `.cursor/` / `.agents/` via a fixed component-type enum (`skill, command, rule, ignore, mcp`) that lives in the `dlt` PyPI package's source (not in this repo, not checked out locally). That enum has no `hook` type today. So the Cursor/Codex hook configs shipped here are **not auto-installed by anything yet** — they're ready-to-use content for when that CLI support lands (or for a user who copies them in by hand). Wiring that installer is explicitly deferred, not part of this change.

## Component

New files under `workbench/init/` (the `init` toolkit — same place `setup-secrets` and the shared MCP server live):

```
workbench/init/hooks/
  hooks.json                       # Claude Code plugin hook manifest — auto-discovered, matcher "Read|Grep|Bash"
  block_secrets_access.py          # Claude/Codex-schema entrypoint (their PreToolUse I/O shape is identical)
  codex-hooks.json                 # Codex hook config content — matcher "Bash" only (Codex has no Read/Grep tool, it shells out)
  cursor-hooks.json                # Cursor hook config content — beforeReadFile + beforeShellExecution
  cursor_block_secrets_access.py   # Cursor-schema entrypoint (different I/O shape than Claude/Codex)
  _secrets_patterns.py             # shared blocklist logic imported by both scripts (single source of truth)
  README.md                        # explains which of these are auto-loaded today vs. inert content
```

No `plugin.json` changes needed — `hooks/hooks.json` is auto-discovered like skills/commands.

**Why one shared script for Claude+Codex**: both platforms' `PreToolUse` hooks use the identical I/O contract — stdin `{"tool_name": ..., "tool_input": {...}}`, and to deny, stdout `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": ...}}`. Cursor's `beforeReadFile`/`beforeShellExecution` hooks use a different shape (`file_path`/`command` at the top level of stdin, `{"permission": "deny", "user_message": ...}` on stdout), so it needs its own entrypoint — but both entrypoints call into the same `_secrets_patterns.py` for the actual matching, so the blocklist is defined once.

## Blocklist (`_secrets_patterns.py`)

Matches this repo's existing dlt secrets convention (`.claudeignore` already lists `secrets.toml`, `*.secrets.toml`) plus generic dotenv files:

- `secrets.toml`, `*.secrets.toml` (any path — covers `.dlt/secrets.toml` and profile-scoped `.dlt/dev.secrets.toml`)
- `.env`, `.env.*` — **except** `.env.example`, `.env.template`, `.env.sample` (placeholders, safe to read)

Matching is done on the **basename** of any path-like token, not the full path, so it catches these files regardless of directory. Exposes two functions used by both entrypoints:

- `is_blocked_path(path: str) -> bool` — for direct file-path args (`Read.file_path`, `Grep.path`/`paths`, Cursor `beforeReadFile.file_path`)
- `command_is_blocked(command: str) -> bool` — tokenizes a shell command (`shlex.split`, falling back to `.split()` on malformed quoting) and checks each token's basename

## Tool coverage

| Agent | Hook event | Matcher / trigger | Field(s) inspected |
|-------|-----------|--------------------|---------------------|
| Claude Code | `PreToolUse` | `"Read\|Grep\|Bash"` | `Read.file_path`, `Grep.path`/`paths`, `Bash.command` |
| Codex | `PreToolUse` | `"Bash"` | `tool_input.command` (Codex has no dedicated Read/Grep tool — file access goes through shell) |
| Cursor | `beforeReadFile` + `beforeShellExecution` | both events | `file_path`, `command` respectively |

`Glob` (Claude) is intentionally not covered — it only lists filenames, doesn't reveal content.

## Decision logic

```
for each candidate path/token extracted from the tool input:
    if is_blocked_path(basename) or command contains a blocked basename:
        deny (schema per-agent, see above), reason points to
        secrets_view_redacted / secrets_update_fragment MCP tools
if nothing matched:
    allow (Claude/Codex: exit 0 no stdout; Cursor: {"permission": "allow"})
```

**Fail-open on script errors**: if stdin isn't valid JSON, or an unexpected exception occurs, the script allows rather than blocking all Read/Grep/Bash calls. A bug in this hook must never brick the agent's ability to read normal files.

## Deny message

```
Blocked: direct access to secrets/env files is not allowed.
Use the dlt-workspace-mcp `secrets_view_redacted` tool to inspect values (redacted)
or `secrets_update_fragment` to write placeholders. See the setup-secrets skill.
```

## Testing

No root-level pytest suite exists in this repo (only `dlthub-evals/` has one, and it's a separate subproject). Verification is manual, run during implementation:

```bash
# Claude / Codex schema
echo '{"tool_name":"Read","tool_input":{"file_path":".dlt/secrets.toml"}}' | python3 workbench/init/hooks/block_secrets_access.py
echo '{"tool_name":"Bash","tool_input":{"command":"cat .env"}}' | python3 workbench/init/hooks/block_secrets_access.py
echo '{"tool_name":"Read","tool_input":{"file_path":".env.example"}}' | python3 workbench/init/hooks/block_secrets_access.py   # should allow

# Cursor schema
echo '{"hook_event_name":"beforeReadFile","file_path":".dlt/secrets.toml"}' | python3 workbench/init/hooks/cursor_block_secrets_access.py
echo '{"hook_event_name":"beforeShellExecution","command":"cat .env"}' | python3 workbench/init/hooks/cursor_block_secrets_access.py
```

Also run `make validate-toolkits` to confirm the new `hooks/` directory doesn't break existing checks (it only enumerates `skills/`, `commands/`, `rules/` per toolkit today, so it shouldn't).

## Non-goals

- Not a sandbox — a determined obfuscation (base64-encoded path, `python -c` reading via variable indirection) can still slip past the `Bash`/`command` token check. This is a deterrent for the common case, not a security boundary.
- No changes to the `dlthub ai` CLI installer — Cursor/Codex auto-wiring is future work in that package.
- No change to `.claudeignore` (stays scoped to dlt secrets only, as today).
- No README.md (repo root) changes — the new `hooks/README.md` inside the component documents status instead.
