# Universal secrets-read guard

`secrets_guard.py` blocks direct reads of dlt secrets and credential files across
**Claude Code, Codex, and Cursor** — one stdlib-only script, no imports, safe to
copy anywhere. See `docs/superpowers/specs/2026-07-01-secrets-read-hook-design.md`
for the design record.

**This hook is a deterrent, not the security boundary.** It catches the
common, low-effort ways an agent reads a secret by mistake or by naive
instruction-following. Shell syntax has no ceiling on cleverness — see
["What still gets through"](#what-still-gets-through) — and no amount of
pattern-matching closes that for good. The actual boundary is OS-level
enforcement this hook cannot be talked around: see
["Pair it with permissions.deny or a sandbox"](#pair-it-with-permissionsdeny-or-a-sandbox)
below.

## What it blocks — files

| Blocked | Still readable |
|---|---|
| `secrets.toml`, `*.secrets.toml` | `example.` / `template.` / `sample.secrets.toml` |
| `.env`, `.env.*`, `.envrc` | `.env.example`, `.env.template`, `.env.sample` |
| `.netrc`, `.pgpass`, `.pypirc`, `.aws/credentials` | `.dlt/config.toml` (not secret) |
| `service_account.json`, `application_default_credentials.json` | `id_*.pub` (public halves) |
| `id_rsa`, `id_dsa`, `id_ecdsa`, `id_ed25519` | anything else |

Matching is on the **basename**, case-insensitively, after stripping editor
backup suffixes (`.bak`, `~`, `.save`, `.orig`, `.swp`, …) — so `SECRETS.TOML`
and `.dlt/secrets.toml.bak` are blocked too. The placeholder exemption is the
whole stem, not a suffix: `example.secrets.toml` is readable,
`dev.example.secrets.toml` is not.

**Symlinks are judged by their target.** A link named `notes.txt` pointing at
`.dlt/secrets.toml` is blocked, and so is a link pointing at a secrets
*directory* (`ln -s .dlt d && grep -r key d`). This needs the payload to carry
`cwd` — all three agents send it — and follows one hop to `os.path.realpath`,
which is already fully resolved.

## What it blocks — commands

| Rule | Denied | Still allowed |
|---|---|---|
| Punctuation is tokenized out | `cat<.env`, `cat .env\|head` | — |
| A newline ends a command | `dlthub ai secrets list`⏎`cat .env` | `git commit -m "fix`⏎`.env loading"` (newline inside quotes) |
| A trailing `\` continues it | `cat \`⏎`.env` | — |
| A grep PATTERN is not a path | `grep api_key .env` | `grep secrets.toml src/` (searches *for* the string) |
| Globs, three ways | `cat .dlt/*`, `cat .env*`, `cat .netr*` | `cat *.toml`, `cat src/*.py` |
| Bulk readers on a secrets dir | `grep -r pw .dlt/`, `tar cf - .dlt` | `ls .dlt` (names, not contents) |
| Inline interpreter code | `bash -c 'cat .env'`, `python3 -c "open('.env')"` | `git commit -m "fix .env loading"` |
| `env` / `printenv` dumps | `env`, `printenv \| grep -i key` | `env FOO=1 cmd`, `env -i ls` |

`env` dumps are blocked because dlt resolves credentials from environment
variables as readily as from `secrets.toml`.

Globs get three checks, cheapest first: the directory the pattern points at,
the shape of the pattern itself (`.env*`, anything containing `secret` or
`credential`), and — only then — what it actually expands onto in `cwd`. The
first two are filesystem-independent, so they hold for a file that does not
exist yet.

## What it blocks — tampering with itself

Bash commands and Write/Edit calls that **rewrite the guard or the config that
installs it** are refused with their own message:

- the script (`secrets_guard.py`) and the configs that register it
  (`.claude/settings.json`, `.claude/settings.local.json`, `.cursor/hooks.json`,
  `.codex/hooks.json`)
- the directories holding them (`rm -rf .claude`, `mv .claude .claude.off`,
  `rm -r .agents/hooks`, `find .claude -delete`) — removing the directory
  disables the guard just as surely as editing the file
- the same names inside an interpreter one-liner
  (`python3 -c "shutil.rmtree('.claude')"`), which the shell tokenizer sees
  only as one opaque quoted blob

Two scopes, deliberately different:

- a guard **file** is protected against any mutation;
- a guard **directory** only against being destroyed or renamed (`rm`, `rmdir`,
  `mv`, `chmod`, `shred`, `find -delete`). `cp -r .claude backup/` reads it and
  `cp x .claude/` adds to it — neither disables the guard.

The check is per command segment, so a mutator in one command does not vouch
for a guard path in another: `rm -rf build && ls .claude` is allowed. Reading
with `cat`, `grep` or `head` is fine, and only the directory itself is the
target — `rm .claude/CLAUDE.md` is untouched. `.codex/config.toml` is
deliberately *not* on the list: Codex hooks live in `.codex/hooks.json`
(openai/codex#17532), so config.toml carries no guard registration and
blocking it would only get in the way.

### The escape hatch is exempt

A guard that refuses the route its own deny message recommends leaves the agent
with no sanctioned way to work with secrets — the state most likely to make it
route around the guard. So these pass, even though they name a secrets file:

```bash
dlthub ai secrets view-redacted --path .dlt/secrets.toml
dlthub ai secrets update-fragment --path .dlt/secrets.toml '<toml>'
uv run dlthub ai secrets list
```

and so do MCP tools whose name ends in `secrets_list`, `secrets_view_redacted`,
or `secrets_update_fragment` (matched by trailing name, so the server can be
called anything).

The exemption is per *command segment*, and a segment ends at an operator, a
newline, or a subshell. So all of these are still denied:

```bash
dlthub ai secrets list && cat .env
dlthub ai secrets list; cat .env
dlthub ai secrets list
cat .env                          # a later line is judged on its own
dlthub ai secrets list $(cat .env)  # so is a subshell
sh -c 'dlthub ai secrets list && cat .env'
```

Only the three redacted subcommands are exempt — any other `dlthub ai secrets`
subcommand fails closed.

Not secret, not restricted: `.dlt/config.toml` reads and edits are always
allowed. The one place it gets caught is a *bulk* read of the whole `.dlt`
directory (`grep -rn destination .dlt/`), which would also read `secrets.toml`
— that denial carries its own message pointing at the direct read.

## How one script serves three agents

The script detects the calling agent from the stdin payload and answers in that
agent's dialect:

| Agent | Detection (`hook_event_name`) | Input fields | Deny output |
|-------|-----------|--------------|-------------|
| Claude Code / Codex | any value that is **not** a Cursor event — `PreToolUse`, an unrecognized value, or absent | `tool_input.command` / `.file_path` / `.path` / `.paths` / `.glob` / `.notebook_path` | `{"hookSpecificOutput": {"permissionDecision": "deny", ...}}` |
| Cursor | `beforeReadFile`, `beforeTabFileRead`, `beforeShellExecution`, `beforeMCPExecution`, `preToolUse` | top-level `file_path` / `command`, or `tool_name` + `tool_input` | `{"permission": "deny", "user_message": ..., "agent_message": ...}` |

The discriminator is the `hook_event_name` **value**, and the comparison is
**case-sensitive on purpose**: Cursor's generic tool event is `preToolUse` while
Claude Code and Codex send `PreToolUse`. Lowercasing event names would route
every Claude call into the Cursor dialect, where the deny JSON has a different
shape and would be silently ignored — a guard that looks installed and blocks
nothing. Don't "normalize" that comparison.

Tools with no dedicated branch (MCP servers, tools added after this script was
written) fall through to a generic scan of every string in `tool_input`,
skipping prose fields like `pattern`, `content`, and `query`. Each string is
judged the same way a shell command is — as a blocked path and as a possible
read or tamper attempt — so a shell-capable tool is caught whatever it calls
its command field, not just one named `command`.

### Failure policy

- **stdin is not a JSON object** — the operation can't be identified, so allow,
  but loudly: traceback on stderr, `{"permission": "allow"}` on stdout, exit 1.
- **A guarded operation that can't be evaluated** (unexpected field types,
  vendor payload drift) — **deny**, fail closed, traceback on stderr.

The deny channel is always the JSON on stdout, never the exit code: in both
Claude Code and Cursor only exit 2 blocks; exit 1 is a non-blocking error and the
action proceeds.

## Limits

### Known false positives

Conservative by design; each of these is denied even though it leaks nothing:

- Any command whose last word is `env` — `cat env`, `ls env`, `rm -rf env`. The
  dump check is basename-based and position-agnostic; tightening it to `argv[0]`
  would open `xargs env`, `sudo env` and `time env`.
- Any command mentioning `printenv`, including `echo printenv`.
- `find .dlt -name '*.toml'`, which only lists names, because `find` is on the
  bulk-reader list. `ls .dlt` is allowed.
- `cat *` in a directory that happens to contain a guarded file.
- Reads of a guard config that use a verb on the mutator list —
  `sed -n '1,5p' .claude/settings.json`, `cp .claude/settings.json /tmp/` — are
  refused as tampering. The verb cannot be told apart from its writing form by
  tokens alone. `cat`, `grep` and `head` are unaffected.
- `cat .ssh/*.pub`, because any glob pointing into a secret directory is
  refused even though the public halves are readable by name.

### What still gets through

Documented on purpose, so nobody mistakes this for a sandbox:

- **Unscoped recursive readers**: `grep -rn api_key .` never names a guarded file.
  (Claude's own `Read` deny rules don't cover this either.) In practice
  `.gitignore` blunts it — dlt workspaces gitignore `secrets.toml` and `.env`, and
  Claude's `Grep` (ripgrep) honors that; plain `grep -r` does not.
- **Indirection**: `cat "$SECRETS"`, or a script that opens the file itself.
  (`cat $(echo .env)` *is* caught — the subshell is judged on its own — but
  backticks are not tokenized, so `` cat `echo .env` `` is not.) Quoting the
  substitution defeats the same check that catches it unquoted: `cat
  "$(echo .env)"` lexes as one opaque word (correct shell-quoting semantics),
  so the split that makes the bare form denyable never happens.
- **Shell word-splitting and expansion**: nothing here replicates bash's own
  expansion, so a guarded name assembled *at shell level* rather than typed
  literally slips through — `cat$IFS.env` (IFS word-splitting), `{cat,.env}`
  or `.dlt/{secrets,config}.toml` (brace expansion), and `cat $'\x2eenv'`
  (ANSI-C hex-escaped quoting) all read the file without a `.env` or
  `secrets.toml` token ever appearing. Closing this for good means parsing
  real bash grammar instead of pattern-matching tokens, which is exactly the
  kind of arms race this hook opts out of — see the top of this file.
- **A glob character laundering a name**: `cat .netrc?` is allowed, because a
  token containing `*`, `?` or `[` is judged as a pattern, never as a literal.
- **Guard tampering through a generic MCP tool's write target**: a payload
  carrying a shell-command-shaped string is tamper-checked regardless of
  which field holds it, but one carrying a `path` *to write to* is only
  checked against the secrets blocklist, not the guard-file list — the
  dedicated write-tool branch checks tampering first, but the generic
  fallback has no notion of "this field is a write target" to check it
  against. Adding guard paths to the generic scan's blocklist would deny
  legitimate reads of `.claude/settings.json` by tools with no write branch.
- **Deeply nested payloads**: the generic scan stops after 6 levels.
- **Unbounded glob cost**: an agent-supplied `~/*/*/*/*/*/*` makes `glob.glob`
  walk the tree, measured at seconds against a ~15 ms startup budget.
- **Anything outside the agent's tool calls** — values already printed into the
  transcript by a pipeline trace or a CLI command.

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

> **Known issue with the `git rev-parse` fallback.** In a workspace with no
> `.git`, `git rev-parse --show-toplevel` climbs to the *parent* repository and
> resolves to the wrong path. The hook command then fails, and because Cursor
> treats a failing hook as an explicit deny, it hard-denies **every** file read
> — not just guarded ones. `dlthub-init` does not `git init` its scaffolds, so
> this is reachable. The candidate fix is to bake the absolute project dir in at
> install time rather than resolving it at run time; it belongs in
> `dlthub-init`'s `hooks.py`, not here.

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

## Pair it with permissions.deny or a sandbox

This hook is portable and cheap, but it is a **deterrent**: every check above
is pattern-matching on text, and text has no ceiling on how it can be shaped
(see "What still gets through"). Nothing in this section is optional polish —
without it, the hook *is* the security boundary, and it was never designed to
be one.

**The actual boundary is OS-level enforcement.** Enable Claude Code's
[sandbox](https://code.claude.com/docs/en/sandboxing): it restricts what a
tool-call subprocess can touch at the kernel level, so it doesn't matter how a
command is spelled — `cat$IFS.env` and `cat .env` hit the same denied syscall.
Where a sandbox isn't available (Codex, Cursor, or a Claude Code version
without it), the equivalent is filesystem permissions the agent's own process
can't override — e.g. secrets readable only by a separate process invoked
through `dlthub ai secrets view-redacted`, not by the agent's shell user.

On Claude Code there's also a **native, still-pattern-based-but-stronger**
layer worth stacking underneath the sandbox: `permissions.deny` rules are
evaluated regardless of what a PreToolUse hook returns, and they cover file
commands Claude recognizes inside Bash and `<` / `>` redirection targets — a
different recognizer than this hook's, so it closes some gaps that overlap
rather than compound.

A plugin manifest can't ship permission rules, so this belongs in the
CLI-generated `.claude/settings.json`, matching this hook's file list:

```json
{
  "permissions": {
    "deny": [
      "Read(**/secrets.toml)",
      "Read(**/*.secrets.toml)",
      "Read(**/.env)",
      "Read(**/.env.*)",
      "Read(**/.envrc)",
      "Read(**/.netrc)",
      "Read(**/_netrc)",
      "Read(**/.pgpass)",
      "Read(**/.pypirc)",
      "Read(**/service_account.json)",
      "Read(**/application_default_credentials.json)",
      "Read(**/id_rsa)",
      "Read(**/id_dsa)",
      "Read(**/id_ecdsa)",
      "Read(**/id_ed25519)",
      "Read(**/.aws/credentials)",
      "Read(**/.azure/credentials)"
    ]
  }
}
```

Trade-off worth knowing before adding it: **deny rules can't carry exceptions**,
so `Read(**/.env.*)` also blocks `.env.example`. The hook keeps the
example/template exemption; the deny rules don't. Decide per rule which matters
more. And these rules cover the `Read` tool only — they're a stronger version
of one slice of what the hook does, not a replacement for it: they have no
equivalent of the hook's bulk-directory or shell-tampering checks, so the
Bash-based reads earlier in this doc still rely on Claude's own file-command
recognition inside Bash, not on this list.

## Testing

```bash
make test     # or: python3 -m unittest tests.test_secrets_guard
```

`tests/test_secrets_guard.py` has two tiers. Most of it calls `deny_reason()`
in process and asserts the **exact** message constant — that is what stops a
refactor from silently swapping `DENY` for `TAMPER`, or denying by crashing.
The rest runs the script as a subprocess to pin the process contract: both
output dialects, allow-is-silence, exit codes, and the fail-open/fail-closed
split.

Manual stdin checks, one per dialect:

```bash
# Claude / Codex dialect (stdin: {tool_name, tool_input}) -> deny JSON
echo '{"tool_name":"Read","tool_input":{"file_path":".dlt/secrets.toml"}}' | python3 secrets_guard.py

# Cursor dialect (stdin: {hook_event_name, file_path|command}) -> {"permission":"deny"}
echo '{"hook_event_name":"beforeShellExecution","command":"cat .env"}' | python3 secrets_guard.py

# Allowed reads produce no output (Claude/Codex) or {"permission": "allow"} (Cursor)
echo '{"tool_name":"Read","tool_input":{"file_path":".env.example"}}' | python3 secrets_guard.py
```
