# Universal secrets-read guard

`secrets_guard.py` blocks direct reads of dlt secrets and credential files across
**Claude Code, Codex, and Cursor** — one stdlib-only script, no imports, safe to
copy anywhere. See `docs/superpowers/specs/2026-07-01-secrets-read-hook-design.md`
for the full design.

## What it blocks

| Blocked | Still readable |
|---|---|
| `secrets.toml`, `*.secrets.toml` | `example.` / `template.` / `sample.secrets.toml` |
| `.env`, `.env.*`, `.envrc` | `.env.example`, `.env.template`, `.env.sample` |
| `.netrc`, `.pgpass`, `.pypirc`, `.aws/credentials` | `.dlt/config.toml` (not secret) |
| `service_account.json`, `application_default_credentials.json` | `id_*.pub` (public halves) |
| `id_rsa`, `id_dsa`, `id_ecdsa`, `id_ed25519` | anything else |

Matching is on the **basename**, case-insensitively, after stripping editor
backup suffixes (`.bak`, `~`, `.save`, `.orig`, `.swp`, …) — so `SECRETS.TOML`
and `.dlt/secrets.toml.bak` are blocked too.

Shell commands get three extra checks beyond "does a token name a guarded file":

- **Punctuation is tokenized out.** `cat<.env` and `cat .env|head` are single
  glued tokens under plain `shlex.split`; the guard uses `punctuation_chars=True`
  so the path becomes visible.
- **Globs are resolved.** A glob whose directory is a secrets dir (`cat .dlt/*`)
  or whose pattern targets guarded names (`cat .env*`) is blocked, as is any
  glob that expands onto a guarded file in the payload's `cwd`.
- **Bulk readers aimed at a secrets directory** (`grep -r password .dlt/`,
  `tar cf - .dlt`) are blocked, while name-only commands (`ls .dlt`) are not.
- **Inline interpreter code** is split open: `bash -c 'cat .env'` and
  `python3 -c "open('.env')"` are blocked. Only tokens after `-c`/`-e` on a real
  interpreter are inspected, so `git commit -m "fix .env loading"` still runs.
- **`env` / `printenv` dumps** are blocked — dlt resolves credentials from
  environment variables as readily as from `secrets.toml`. `env FOO=1 cmd` (the
  prefix form) still runs.

The guard also refuses tool calls that **rewrite the guard or its config**
(`rm .agents/hooks/secrets_guard.py`, `sed -i … .claude/settings.json`, an `Edit`
on either). Reading those files is fine; only mutating them is refused.

## How one script serves three agents

The script detects the calling agent from the stdin payload and answers in that
agent's dialect:

| Agent | Detection (`hook_event_name`) | Input fields | Deny output |
|-------|-----------|--------------|-------------|
| Claude Code / Codex | `PreToolUse`, or absent | `tool_input.file_path` / `.paths` / `.glob` / `.command` | `{"hookSpecificOutput": {"permissionDecision": "deny", ...}}` |
| Cursor | `beforeReadFile`, `beforeTabFileRead`, `beforeShellExecution`, `beforeMCPExecution`, `preToolUse` | top-level `file_path` / `command`, or `tool_name` + `tool_input` | `{"permission": "deny", "user_message": ..., "agent_message": ...}` |

The discriminator is the `hook_event_name` **value**, and the comparison is
**case-sensitive on purpose**: Cursor's generic tool event is `preToolUse` while
Claude Code and Codex send `PreToolUse`. Lowercasing event names would route
every Claude call into the Cursor dialect, where the deny JSON has a different
shape and would be silently ignored — a guard that looks installed and blocks
nothing. Don't "normalize" that comparison.

Tools with no dedicated branch (MCP servers, tools added after this script was
written) fall through to a generic scan of every path-shaped string in
`tool_input`, skipping prose fields like `pattern`, `content`, and `query`.

### Failure policy

- **stdin is not a JSON object** — the operation can't be identified, so allow,
  but loudly: traceback on stderr, `{"permission": "allow"}` on stdout, exit 1.
- **A guarded operation that can't be evaluated** (unexpected field types,
  vendor payload drift) — **deny**, fail closed, traceback on stderr.

The deny channel is always the JSON on stdout, never the exit code: in both
Claude Code and Cursor only exit 2 blocks; exit 1 is a non-blocking error and the
action proceeds.

## Delivery channels — and why the two paths differ

| Channel | Config | Script path in the command | Agents |
|---|---|---|---|
| Claude Code marketplace | `hooks.json` here, auto-discovered on plugin install | `"${CLAUDE_PLUGIN_ROOT}"/hooks/secrets_guard.py` | Claude only |
| `dlthub ai hooks install` | synthesized per agent (`.claude/settings.json`, `.cursor/hooks.json`, `.codex/hooks.json`) | `"$CLAUDE_PROJECT_DIR"/.agents/hooks/secrets_guard.py`, or `"$(git rev-parse --show-toplevel \|\| pwd)"` for Cursor/Codex | all three |

**This difference is intended, not drift.** The two channels put the script in
two different places, so they must point at two different paths:

- The plugin channel runs the copy *inside the installed plugin*. It needs no
  file copy, and the guard updates when the plugin updates.
- The CLI channel copies the script into the workspace at
  `.agents/hooks/secrets_guard.py`, because Cursor and Codex have no
  `CLAUDE_PLUGIN_ROOT` (nor any project-root variable — hence the `git rev-parse`
  fallback) and each needs a differently-shaped config file. Those config shapes
  are generated in the CLI's own code, which is why this directory ships no
  Cursor/Codex templates: one definition, no drift.

`hooks.json` is therefore Claude-plugin-only, and the CLI ignoring it is correct.
Two consequences to know:

1. **A workspace can get the guard from both channels.** It then runs twice per
   Claude tool call — harmless (same deny, allows are silent), just expected.
2. **The workspace copy is a snapshot.** Per dlthub-init PR #8 the installer does
   not overwrite an existing `.agents/hooks/secrets_guard.py`, so it never
   clobbers a user's edit — but it also means a workspace keeps whatever version
   it was scaffolded with. To pick up changes to this file, delete the workspace
   copy and re-run the installer. (Re-verify this against the current
   `dlthub ai hooks install` before relying on it; the behaviour is defined in
   that CLI, not here.)

`matcher` here is `"*"` (all tools) rather than `Read|Grep|Bash`. PreToolUse fires
for MCP tools and for subagent tool calls, and a filesystem-ish MCP server reading
`.dlt/secrets.toml` is exactly the case a narrow matcher misses. Cost is one
Python start per tool call — measured at ~15 ms.

## Pair it with `permissions.deny` (Claude Code only)

This hook is the portable layer. On Claude Code a **stronger** native layer
exists and should be used alongside it — deny rules are evaluated regardless of
what a PreToolUse hook returns, and they cover three things a token matcher
can't: file commands Claude recognizes inside Bash, `<` / `>` redirection
targets, and symlinks (both the link and what it resolves to).

A plugin manifest can't ship permission rules, so this belongs in the
CLI-generated `.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Read(**/secrets.toml)",
      "Read(**/*.secrets.toml)",
      "Read(**/.env)",
      "Read(**/.env.*)",
      "Read(**/.envrc)"
    ]
  }
}
```

Trade-off worth knowing before adding it: **deny rules can't carry exceptions**,
so `Read(**/.env.*)` also blocks `.env.example`. The hook keeps the
example/template exemption; the deny rules don't. Decide per rule which matters
more.

For an actual boundary rather than a deterrent, enable Claude Code's
[sandbox](https://code.claude.com/docs/en/sandboxing) — OS-level enforcement that
applies to every process, including ones this hook can't see.

## What still gets through

Documented on purpose, so nobody mistakes this for a sandbox:

- **Unscoped recursive readers**: `grep -rn api_key .` never names a guarded file.
  (Claude's own `Read` deny rules don't cover this either.) In practice
  `.gitignore` blunts it — dlt workspaces gitignore `secrets.toml` and `.env`, and
  Claude's `Grep` (ripgrep) honors that; plain `grep -r` does not.
- **Indirection**: `cat "$SECRETS"`, or a script that opens the file itself.
- **Anything outside the agent's tool calls** — values already printed into the
  transcript by a pipeline trace or a CLI command.

## Manual testing

```bash
# Claude / Codex dialect (stdin: {tool_name, tool_input}) -> deny JSON
echo '{"tool_name":"Read","tool_input":{"file_path":".dlt/secrets.toml"}}' | python3 secrets_guard.py

# Cursor dialect (stdin: {hook_event_name, file_path|command}) -> {"permission":"deny"}
echo '{"hook_event_name":"beforeShellExecution","command":"cat .env"}' | python3 secrets_guard.py

# Allowed reads produce no output (Claude/Codex) or {"permission": "allow"} (Cursor)
echo '{"tool_name":"Read","tool_input":{"file_path":".env.example"}}' | python3 secrets_guard.py
```

The full matrix — every bypass above, plus the false-positive cases that must
stay allowed — lives in `tests/test_secrets_guard.py`:

```bash
python3 -m unittest tests.test_secrets_guard
```
