# Universal secrets-read guard for Claude Code, Codex, and Cursor

## Problem

`setup-secrets` already documents a policy: "Never read secrets files directly — use `dlt-workspace-mcp` tools or `dlthub ai secrets` CLI commands." This is prompt-level only — nothing stops an agent from running `cat .dlt/secrets.toml`, `Read(".env")`, or `Grep` over a secrets file and leaking real values into the transcript. We want a technical enforcement layer, not just an instruction, across all three supported agents: Claude Code, Cursor, Codex.

## Architecture: one script, two repos

**One universal script** (`workbench/init/hooks/secrets_guard.py`) serves all three agents. It is stdlib-only with no sibling imports, so it can be copied anywhere as a single file. It detects the calling agent from the stdin payload shape and answers in that agent's dialect.

**Two delivery channels:**

1. **Claude Code marketplace (works today)** — Claude Code plugins auto-discover `hooks/hooks.json` at the plugin root and load it on install. `workbench/init/hooks/hooks.json` registers the script with matcher `"*"` (all tools), using `${CLAUDE_PLUGIN_ROOT}` for the path. The matcher is deliberately not `"Read|Grep|Bash"`: PreToolUse also fires for MCP tools and subagent tool calls, and a filesystem-ish MCP server reading `.dlt/secrets.toml` is exactly what a narrow matcher misses. Measured cost is ~15 ms of Python start per tool call.
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
| Cursor | `hook_event_name` ∈ {`beforeReadFile`, `beforeTabFileRead`, `beforeShellExecution`, `beforeMCPExecution`, `preToolUse`} | top-level `file_path` / `command`, or `tool_name` + `tool_input` | `{"permission": "deny", "user_message": ..., "agent_message": ...}` | `{"permission": "allow"}` |

Claude Code and Codex share the identical PreToolUse I/O contract, so one dialect covers both — verified against `codex-rs`: the shell tool serializes `tool_name: "Bash"` with `tool_input.command` as a **string** (`HookToolName::bash()`, `core/src/tools/sandboxing.rs`), and the generated `pre-tool-use.command.output.schema.json` accepts `hookSpecificOutput.permissionDecision: "deny"`. Codex has no dedicated Read/Grep tool (file access goes through shell), but it does emit PreToolUse for `apply_patch` (canonical name; `Write`/`Edit` are matcher aliases only) and for MCP tools, which the guard's write-tool and generic branches cover.

The event comparison is **case-sensitive on purpose**: Cursor's generic tool event is `preToolUse`, Claude Code's and Codex's is `PreToolUse`. Lowercasing event names would route every Claude call into the Cursor dialect, whose deny JSON Claude ignores — a guard that looks installed and blocks nothing.

## Blocklist

Matches this repo's existing dlt secrets convention (`.claudeignore` already lists `secrets.toml`, `*.secrets.toml`) plus generic dotenv and credential files:

- `secrets.toml`, `*.secrets.toml` (any path — covers `.dlt/secrets.toml` and profile-scoped `.dlt/dev.secrets.toml`). Note: the bare name needs an explicit equality check — a `*.secrets.toml` glob alone does not match `secrets.toml` (too short for the pattern).
- `.env`, `.env.*`, `.envrc` — **except** `.env.example`, `.env.template`, `.env.sample` (placeholders, safe to read). The same placeholder exemption applies to `*.secrets.toml`.
- Credential files common in dlt workspaces: `.netrc`, `.pgpass`, `.pypirc`, `.aws/credentials`, `service_account.json`, `application_default_credentials.json`, and default ssh private key names (`id_rsa`, `id_dsa`, `id_ecdsa`, `id_ed25519` — `.pub` halves stay readable). `*.pem` / `*.key` are deliberately **not** blocked: too many legitimate certs and fixtures carry those extensions.

Matching is done on the **basename** of any path-like token, not the full path, so it catches these files regardless of directory. Basenames are lowercased (macOS/Windows resolve `SECRETS.TOML` and `secrets.toml` to the same file) and stripped of editor backup suffixes (`.bak`, `~`, `.save`, `.orig`, `.swp`, …), so `secrets.toml.bak` is blocked and `.env.example.bak` is not.

Shell commands are tokenized with `shlex` configured with `punctuation_chars=True`, not `shlex.split`. Plain `shlex.split` returns `cat<.env` and `cat .env|head` as single glued tokens whose basename matches nothing — both are valid bash that reads the file. On malformed quoting the fallback is a whitespace split with quote characters stripped. Four further shell checks:

- **Glob tokens** are blocked when their directory is a secrets dir (`cat .dlt/*`), when the pattern itself targets guarded names (`cat .env*`, anything containing `secret`/`credential`), or when expanding them against the payload's `cwd` hits a guarded file. A bare `*.toml` or `*` is judged by expansion alone, so `cat *.toml` in a project root stays allowed.
- **Bulk readers** (`cat`, `grep`, `rg`, `find`, `tar`, `cp`, `base64`, …) pointed at a secrets *directory* (`.dlt`, `.ssh`, `.gnupg`, `.aws`) are blocked, since they leak without naming a guarded file. Name-only commands like `ls .dlt` are not.
- **Inline interpreter code** after `-c`/`-e` on a real interpreter is split open, catching `bash -c 'cat .env'` and `python3 -c "open('.env')"`. Restricting it to interpreters keeps `git commit -m "fix .env loading"` allowed.
- **`env` / `printenv` dumps** are blocked: dlt resolves credentials from environment variables as readily as from `secrets.toml`, so `env | grep -i key` leaks exactly what this guard protects. The prefix form `env FOO=1 cmd` still runs.

Tool calls that rewrite the guard itself or the config that installs it (`secrets_guard.py`, `.claude/settings.json`, `.cursor/hooks.json`, `.codex/hooks.json`, `.codex/config.toml`) are refused with a separate message. Reading them is allowed; only mutation is refused.

Tools with no dedicated branch fall through to a generic scan of every path-shaped string in `tool_input`, skipping prose fields (`pattern`, `content`, `query`, …) where a mention of `.env` is not an access.

`Glob` (Claude) is intentionally not covered — it only lists filenames, doesn't reveal content.

## Failure policy

Split by whether the payload names an operation we are supposed to judge:

- **stdin is not a JSON object** — the operation cannot be identified, so allow, but never silently: traceback on stderr, `{"permission": "allow"}` on stdout, exit 1. A guard that can't parse its input must not brick the agent's ability to read normal files.
- **The payload identifies a guarded operation but evaluating it raises** (unexpected field types, vendor payload drift) — **deny, fail closed**, traceback on stderr. Silence here would mean an unreadable payload is a free pass, which is the one case an attacker or a vendor change can arrange.

The deny channel is always the JSON on stdout, never the exit code: Claude Code, Codex, and Cursor all treat exit 1 as a non-blocking error and only exit 2 as a block.

Cursor additionally supports `failClosed: true` on a hook definition (its default is fail-open on crash/timeout/invalid JSON), which the generated `.cursor/hooks.json` should set.

## Path/cwd caveat (dlthub-init phase)

The three agents give no common guarantee about the hook process's working directory. Claude Code has `${CLAUDE_PLUGIN_ROOT}` (plugin path) / `${CLAUDE_PROJECT_DIR}` (project settings); Codex and Cursor expose no such variable, so the scaffolder's generated commands resolve the project root via `$(git rev-parse --show-toplevel 2>/dev/null || pwd)`. The per-agent config shapes for Cursor/Codex are generated in code by dlthub-init's `hooks.py` — the workbench deliberately ships no Cursor/Codex config templates, so the shape is defined in exactly one place. Codex-specific: hooks go in `.codex/hooks.json`, **not** `.codex/config.toml [hooks]`, due to open upstream bug openai/codex#17532 (repo-local config.toml hooks don't fire in interactive sessions).

A project that gets the guard from both channels (scaffolded by dlthub-init *and* `init` plugin installed from the marketplace) registers it twice for Claude — it runs twice per tool call, harmlessly (same deny, silent allow).

## Testing

`tests/test_secrets_guard.py` runs the guard as a subprocess against a real temp dlt workspace (`.dlt/secrets.toml`, `.dlt/example.secrets.toml`, `.dlt/config.toml`, `.env`, `.env.example`, `src/`), so glob expansion has something to expand onto. It covers both dialects and three groups that must all hold together:

1. every bypass listed under Blocklist is denied,
2. the false-positive cases stay allowed (`cat *.toml`, `cat src/*.py`, `ls .dlt`, `env FOO=1 cmd`, `git commit -m "fix .env loading"`, a Grep whose *pattern* is the literal string `secrets.toml`, writes to source files),
3. the failure policy behaves as specified in both directions.

```bash
python3 -m unittest tests.test_secrets_guard
```

Plus manual stdin tests per dialect (see `workbench/init/hooks/README.md`) and a live smoke test in a real session. `make validate-toolkits` must stay clean.

## Non-goals

- Not a sandbox. Indirection through variables (`cat "$SECRETS"`), a script that opens the file itself, and unscoped recursive readers (`grep -rn api_key .`) still get through — Claude Code's own `Read` deny rules don't cover the last one either. Deterrent for the common case, not a security boundary; for a real boundary, enable Claude Code's sandbox.
- Not the only layer on Claude Code. `permissions.deny` is strictly stronger (evaluated regardless of what a PreToolUse hook returns, and it covers file commands inside Bash, redirection targets, and symlinks) and should be written into the CLI-generated `.claude/settings.json` alongside this hook. A plugin manifest cannot ship permission rules, so it cannot come from this repo. Trade-off: deny rules carry no exceptions, so `Read(**/.env.*)` also blocks `.env.example`, which the hook exempts.
- No `dlthub ai` CLI changes.
- No change to `.claudeignore`.
