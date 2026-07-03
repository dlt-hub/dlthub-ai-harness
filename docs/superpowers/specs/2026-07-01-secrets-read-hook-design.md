# Universal secrets-read guard for Claude Code, Codex, and Cursor

## Problem

`setup-secrets` already documents a policy: "Never read secrets files directly — use `dlt-workspace-mcp` tools or `dlthub ai secrets` CLI commands." This is prompt-level only — nothing stops an agent from running `cat .dlt/secrets.toml`, `Read(".env")`, or `Grep` over a secrets file and leaking real values into the transcript. We want a technical enforcement layer, not just an instruction, across all three supported agents: Claude Code, Cursor, Codex.

## Architecture: one script, two repos

**One universal script** (`workbench/init/hooks/secrets_guard.py`) serves all three agents. It is stdlib-only with no sibling imports, so it can be copied anywhere as a single file. It detects the calling agent from the stdin payload shape and answers in that agent's dialect.

**Two delivery channels:**

1. **Claude Code marketplace (works today)** — Claude Code plugins auto-discover `hooks/hooks.json` at the plugin root and load it on install. `workbench/init/hooks/hooks.json` registers the script with matcher `"Read|Grep|Bash"`, using `${CLAUDE_PLUGIN_ROOT}` for the path.
2. **`dlthub-init` scaffolder (separate PR against `dlt-hub/dlthub-init`)** — the scaffolder already syncs skills from this workbench into its wheel (`scripts/generate_skills.py` → repo-root `skills/` → `_bundled_skills/` in the wheel) and installs them into `.agents/skills/` with links into `.claude/skills/`. Hooks follow the same pattern: sync `secrets_guard.py`, bundle it, and at scaffold time copy it to `.agents/hooks/secrets_guard.py` and write per-agent hook configs pointing at it:
   - `.claude/settings.json` — `hooks.PreToolUse` block (merged with existing content, respecting `collisions.py` conventions)
   - `.cursor/hooks.json` — `beforeReadFile` + `beforeShellExecution`
   - `.codex/hooks.json` — `PreToolUse`, matcher `Bash`

The `dlthub ai` CLI (in the `dlt` PyPI package) is a possible third channel later — its component-type enum (`skill, command, rule, ignore, mcp`) has no `hook` type today. Out of scope.

## Dialect detection

The discriminator is the `hook_event_name` **value**, not its presence — Claude Code also sends `hook_event_name` (as `"PreToolUse"`):

| Agent | Detection | Input | Deny output | Allow output |
|-------|-----------|-------|-------------|--------------|
| Claude Code / Codex | `hook_event_name` not a Cursor event; dispatch on `tool_name` | `tool_input.file_path` (Read), `tool_input.path`/`paths` (Grep), `tool_input.command` (Bash) | `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": ...}}` | silence, exit 0 |
| Cursor | `hook_event_name` ∈ {`beforeReadFile`, `beforeShellExecution`} | top-level `file_path` / `command` | `{"permission": "deny", "user_message": ...}` | `{"permission": "allow"}` |

Claude Code and Codex share the identical PreToolUse I/O contract, so one dialect covers both. Codex has no dedicated Read/Grep tool (file access goes through shell), so its config matches on `Bash` only.

## Blocklist

Matches this repo's existing dlt secrets convention (`.claudeignore` already lists `secrets.toml`, `*.secrets.toml`) plus generic dotenv files:

- `secrets.toml`, `*.secrets.toml` (any path — covers `.dlt/secrets.toml` and profile-scoped `.dlt/dev.secrets.toml`). Note: the bare name needs an explicit equality check — a `*.secrets.toml` glob alone does not match `secrets.toml` (too short for the pattern).
- `.env`, `.env.*` — **except** `.env.example`, `.env.template`, `.env.sample` (placeholders, safe to read)

Matching is done on the **basename** of any path-like token, not the full path, so it catches these files regardless of directory.

Shell commands are tokenized with `shlex.split` (falling back to `.split()` on malformed quoting) — plain whitespace splitting would leave quote characters glued to tokens (`cat ".env"` → `'".env"'`), silently defeating exact-name matching. `Glob` (Claude) is intentionally not covered — it only lists filenames, doesn't reveal content.

## Fail-open

Any unhandled error (bad JSON on stdin, unexpected payload shape) results in exit 0 with no output — allow. A bug in this guard must never brick the agent's ability to read normal files. This matches Claude Code's own semantics (non-zero/non-two exit codes are non-blocking) and Cursor's fail-open default.

## Path/cwd caveat (dlthub-init phase)

The three agents give no common guarantee about the hook process's working directory. Claude Code has `${CLAUDE_PLUGIN_ROOT}` (plugin path) / `${CLAUDE_PROJECT_DIR}` (project settings); Codex and Cursor expose no such variable. The `codex-hooks.json` / `cursor-hooks.json` files in the workbench are templates with bare-filename commands; the scaffolder must write configs with paths that resolve at runtime (verified per agent during the dlthub-init implementation). Codex-specific: hooks go in `.codex/hooks.json`, **not** `.codex/config.toml [hooks]`, due to open upstream bug openai/codex#17532 (repo-local config.toml hooks don't fire in interactive sessions).

## Testing

Manual stdin tests per dialect (see `workbench/init/hooks/README.md`), plus a live smoke test: temporarily wiring the script into this repo's own `.claude/settings.json` and confirming a real `Read(".env")` and `Bash("cat .env")` are denied while normal reads pass. `make validate-toolkits` must stay clean.

## Non-goals

- Not a sandbox — obfuscation (base64 paths, indirection through variables) can slip past the token check. Deterrent for the common case, not a security boundary.
- No `dlthub ai` CLI changes.
- No change to `.claudeignore`.
