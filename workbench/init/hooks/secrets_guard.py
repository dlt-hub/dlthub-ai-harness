#!/usr/bin/env python3
"""Universal secrets-read guard for Claude Code, Codex, and Cursor hooks.

One stdlib-only file, no sibling imports — safe to copy anywhere. It is copied
verbatim into user workspaces (`.agents/hooks/secrets_guard.py`) where no
README travels with it, so this docstring carries what a reader needs to judge
it alone. Full reference: `workbench/init/hooks/README.md` in
dlt-hub/dlthub-ai-harness.

Refuses four things, each with its own message: reads of secrets/dotenv/
credential files, bulk reads of a directory whose contents are secret,
`env`/`printenv` dumps (dlt resolves credentials from the environment too),
and tool calls that rewrite the guard or the config installing it. The
sanctioned redacted-access route (`dlthub ai secrets view-redacted`, and MCP
tools named `*secrets_view_redacted`) stays exempt — a guard that refuses its
own escape hatch invites being worked around.

Dialects, detected from the stdin payload and answered in kind:

- Claude Code / Codex (PreToolUse): {"tool_name", "tool_input"} in; deny via
  {"hookSpecificOutput": {"permissionDecision": "deny", ...}}; allow is silence.
- Cursor (beforeReadFile / beforeTabFileRead / beforeShellExecution /
  beforeMCPExecution / preToolUse): deny via {"permission": "deny", ...},
  allow via {"permission": "allow"}.

The discriminator is the `hook_event_name` VALUE and the comparison is
case-sensitive on purpose: Cursor's generic tool event is `preToolUse` while
Claude Code and Codex send `PreToolUse`. Lowercasing would route every Claude
call into the Cursor dialect, whose deny JSON Claude ignores — a guard that
looks installed and blocks nothing. Any other event value routes to Claude.

Failure policy, split by whether the payload names an operation to judge:
- stdin is not a JSON object: the operation cannot be identified, so allow —
  but loudly (traceback on stderr, {"permission": "allow"} on stdout, exit 1).
- the payload identifies a guarded operation but evaluating it raises: deny
  (fail closed) in the caller's dialect, traceback on stderr.

The deny channel is always the JSON on stdout, never the exit code: in both
Claude Code and Cursor only exit 2 blocks; exit 1 is a non-blocking error and
the action proceeds.

This is a deterrent, not a sandbox. Indirection (`cat "$SECRETS"`, a script
that opens the file itself) and unscoped recursive readers (`grep -r key .`)
still get through — see README.md for the layers that do close those.
"""

import glob
import json
import os
import re
import shlex
import sys
import traceback

# --- dialect ---------------------------------------------------------------

# Case-sensitive on purpose: Cursor's generic tool event is "preToolUse" while
# Claude Code and Codex send "PreToolUse". Lowercasing these would route every
# Claude call into the Cursor dialect, where a deny is spelled differently and
# would be silently ignored.
_CURSOR_EVENTS = {
    "beforeReadFile",
    "beforeTabFileRead",
    "beforeShellExecution",
    "beforeMCPExecution",
    "preToolUse",
}
_CURSOR_FILE_EVENTS = {"beforeReadFile", "beforeTabFileRead"}

# --- what counts as a secret -----------------------------------------------

_PLACEHOLDER_SUFFIXES = {"example", "template", "sample"}
_BACKUP_SUFFIXES = (".bak", ".backup", ".save", ".orig", ".old", ".tmp", ".swp", ".swo", "~")

_BLOCKED_NAMES = {
    "secrets.toml",
    ".env",
    ".envrc",  # direnv: holds `export AWS_SECRET_ACCESS_KEY=...` lines
    ".netrc",
    "_netrc",
    ".pgpass",
    ".pypirc",
    "service_account.json",  # dlt BigQuery / GCS credentials
    "application_default_credentials.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
# (parent directory, file name): the bare name is too common to block outright
_BLOCKED_IN_DIR = {(".aws", "credentials"), (".azure", "credentials")}

# Directories whose contents are secret: a bulk reader aimed at one of these
# leaks without ever naming a guarded file (`grep -r password .dlt/`).
_SECRET_DIRS = {".dlt", ".ssh", ".gnupg", ".aws"}

# --- shell vocabulary ------------------------------------------------------

_BULK_READERS = {
    "cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg",
    "find", "awk", "sed", "tar", "zip", "base64", "xxd", "od", "strings",
    "cp", "rsync", "tee",
}
_MUTATORS = {"rm", "mv", "cp", "sed", "tee", "truncate", "chmod", "dd", "ln", "shred", "unlink"}
_INTERPRETERS = {
    "sh", "bash", "zsh", "dash", "ksh", "fish", "python", "python2", "python3",
    "node", "deno", "bun", "ruby", "perl", "php",
}
_CODE_FLAGS = {"-c", "-e", "--command", "--eval"}
_CODE_SPLIT = re.compile(r"""[\s"'(),;=\[\]{}]+""")
_OPERATORS = {"|", "||", "&&", ";", "&", ">", ">>", "<", "<<"}
# Output redirections only — the subset of _OPERATORS that writes. Widening
# this to _OPERATORS would make `cat .claude/settings.json | head` a tamper.
_WRITE_REDIRECTS = {">", ">>"}
_GLOB_CHARS = "*?["

# --- the guard's own files -------------------------------------------------

# Files that switch this guard off; a tool call that rewrites them is refused.
_GUARD_FILES = {"secrets_guard.py"}
# Only files that actually register the guard. `.codex/config.toml` is
# deliberately absent: Codex hooks live in `.codex/hooks.json` (config.toml
# hooks don't fire — openai/codex#17532), so guarding it would block ordinary
# Codex configuration work and protect nothing.
_GUARD_CONFIGS = {
    (".claude", "settings.json"),
    (".claude", "settings.local.json"),
    (".cursor", "hooks.json"),
    (".codex", "hooks.json"),
}
_WRITE_TOOLS = {"write", "edit", "multiedit", "notebookedit", "apply_patch"}

# --- the sanctioned escape hatch -------------------------------------------

# Matched by trailing tool name so the MCP server can be called anything,
# consistent with the deny message not naming one.
_SAFE_TOOL_SUFFIXES = ("secrets_list", "secrets_view_redacted", "secrets_update_fragment")
_SAFE_CLI_SUBCOMMANDS = {"list", "view-redacted", "update-fragment"}
_CLI_RUNNERS = {"uv", "uvx", "poetry", "pipx", "run", "exec", "--"}

# --- generic payload scanning ----------------------------------------------

# Payload fields that carry prose rather than paths. Scanning them produces
# false denials (a Grep for the literal string "secrets.toml", a commit message
# that mentions .env) without adding protection.
_PROSE_KEYS = {
    "pattern", "content", "new_string", "old_string", "prompt", "description",
    "message", "body", "text", "query", "instructions", "explanation", "thought",
}
_MAX_SCAN_DEPTH = 6

_SHELL_TOOLS = {"bash", "shell", "powershell"}

DENY_MESSAGE = (
    "Blocked: direct access to secrets/env files is not allowed. "
    "Inspect them with `dlthub ai secrets list` and `dlthub ai secrets view-redacted`, "
    "and write placeholders with "
    "`dlthub ai secrets update-fragment --path <file> '<toml>'`. "
    "If a dlt workspace MCP server is connected, its secrets_view_redacted and "
    "secrets_update_fragment tools do the same with richer output."
)

DIRECTORY_MESSAGE = (
    "Blocked: this reads every file in a directory that holds secrets. "
    "Read the specific file you need directly — non-secret files such as "
    "`.dlt/config.toml` are not restricted — or use "
    "`dlthub ai secrets view-redacted` for the secrets themselves."
)

TAMPER_MESSAGE = (
    "Blocked: this would modify the secrets guard hook or the config that "
    "installs it. If disabling the guard is really intended, ask the user to "
    "do it themselves."
)


# --- path policy: is this name guarded? ------------------------------------


def _basename(token: str) -> str:
    """Lowercased final path segment, Windows separators included.

    Lowercased because macOS/Windows resolve SECRETS.TOML and secrets.toml to
    the same file; backslashes normalized so a Windows path still matches.
    """
    return os.path.basename(token.replace("\\", "/")).lower()


def _path_segments(path: str) -> list[str]:
    return [seg for seg in path.replace("\\", "/").split("/") if seg not in ("", ".")]


def _name_and_parent(path: str) -> tuple[str, str]:
    """Lowercased basename and its parent directory name; ("", "") if empty.

    The empty parent makes the (parent, name) tables miss on a single-segment
    path rather than matching by accident.
    """
    segments = _path_segments(path)
    if not segments:
        return "", ""
    return segments[-1].lower(), (segments[-2].lower() if len(segments) > 1 else "")


def _strip_backup_suffixes(name: str) -> str:
    """`secrets.toml.bak` -> `secrets.toml`, `.env~` -> `.env`.

    Repeats until nothing matches, so `secrets.toml.bak.bak` strips too.
    """
    while True:
        for suffix in _BACKUP_SUFFIXES:
            # never strip to "": `.bak` and `~` are judged as the names they are
            if name.endswith(suffix) and len(name) > len(suffix):
                name = name[: -len(suffix)]
                break
        else:
            return name


def _is_blocked_name(name: str, parent: str) -> bool:
    """True if an already-lowercased, backup-suffix-stripped basename (plus
    its parent directory name) names a guarded secrets/dotenv/credential file."""
    if name in _BLOCKED_NAMES:
        return True
    if (parent, name) in _BLOCKED_IN_DIR:
        return True
    if name.endswith(".secrets.toml"):
        return name[: -len(".secrets.toml")] not in _PLACEHOLDER_SUFFIXES
    if name.startswith(".env."):
        return name.rsplit(".", 1)[-1] not in _PLACEHOLDER_SUFFIXES
    return False


def _names_blocked_file(path: str) -> bool:
    """Name-only verdict. Touches no filesystem, so it is safe on any string."""
    name, parent = _name_and_parent(path)
    return bool(name) and _is_blocked_name(_strip_backup_suffixes(name), parent)


def _resolve(path: str, cwd: str) -> str:
    """`path` against `cwd`, with `~` expanded.

    No isabs branch needed: os.path.join returns an already-absolute second
    argument unchanged, which is also what makes `~/...` work after expansion.
    """
    return os.path.join(cwd, os.path.expanduser(path))


def _is_blocked_path(path: str, cwd: str | None = None) -> bool:
    """True if `path` names a dlt secrets, dotenv, or credential file.

    With `cwd`, a symlink is judged by its real target too: an alias named
    `notes.txt` pointing at `secrets.toml` is blocked by what it resolves to,
    not by its innocent name. Without `cwd` the check is name-only and touches
    no filesystem — that is what caps resolution at one hop (realpath is
    already fully resolved) and keeps the common path syscall-free.
    """
    if not isinstance(path, str):
        raise TypeError("path is not a string")
    if _names_blocked_file(path):
        return True
    if cwd is None:
        return False
    candidate = _resolve(path, cwd)
    return os.path.islink(candidate) and _names_blocked_file(os.path.realpath(candidate))


def _is_secret_dir(path: str) -> bool:
    """True if `path` names a directory whose whole contents are secret."""
    name, _ = _name_and_parent(path)
    return name in _SECRET_DIRS


def _is_guard_path(path: str) -> bool:
    """True if `path` is this guard or the config that installs it."""
    name, parent = _name_and_parent(path)
    return name in _GUARD_FILES or (parent, name) in _GUARD_CONFIGS


# --- shell policy: what does this command touch? ---------------------------


def _tokenize(command: str) -> list[str]:
    """Split a shell command, keeping punctuation as separate tokens.

    punctuation_chars is what makes `cat<.env` and `cat .env|head` visible:
    plain shlex.split returns them as single glued tokens whose basename
    matches nothing.
    """
    # shlex treats a None instream as "read sys.stdin" (still true on 3.13), so
    # a Cursor payload with "command": null would silently lex the drained
    # stdin instead of failing. Raise instead, so the caller fails closed.
    if not isinstance(command, str):
        raise TypeError("command is not a string")
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        # Broken quoting — bash would reject it too, but strip the quote
        # characters so a half-quoted path still matches.
        return [token.strip("\"'") for token in command.split()]


def _basenames(tokens: list[str]) -> set[str]:
    return {_basename(token) for token in tokens}


def _command_segments(tokens: list[str]) -> list[list[str]]:
    """Split a token list on shell operators, so each command is judged alone.

    Without this, `dlthub ai secrets list && cat .env` would inherit the safe
    verdict of its first command.
    """
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _OPERATORS:  # a shell operator ends the current command
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _glob_is_blocked(token: str, cwd: str) -> bool:
    """True if a glob token can expand onto a guarded file.

    Three arms, cheapest first: the directory it points at, the shape of the
    pattern itself, and — only then — actual expansion against `cwd`. The
    first two are filesystem-independent, so they hold for a file that does
    not exist yet.
    """
    normalized = token.replace("\\", "/")
    pattern = _basename(normalized)

    # `cat .dlt/*` names no guarded file; blocked by the directory it targets
    if _is_secret_dir(os.path.dirname(normalized)):
        return True

    # The pattern itself is aimed at guarded names (`cat .env*`). Restricted to
    # secrets-shaped patterns — a bare `*.toml` or `*` is judged by expansion
    # alone, or `cat *.toml` in a project root would be refused.
    if pattern.startswith(".env") or "secret" in pattern or "credential" in pattern:
        return True

    # Last: what it actually expands onto right now.
    matches = glob.glob(_resolve(token, cwd))
    return any(_is_blocked_path(match, cwd) or _is_secret_dir(match) for match in matches)


def _env_dumps(rest: list[str]) -> bool:
    """True if `env` has no command to run — `env`, `env -i`, `env | grep`.

    `env FOO=1 python x` and `env -u FOO cmd` run a command instead of
    printing the environment, so the first bare non-flag word means allow.
    """
    for token in rest:
        if token in _OPERATORS:
            return True
        if not token.startswith("-") and "=" not in token:
            return False  # an operand: this is `env <cmd>`, not a dump
    return True  # ran out of tokens with no operand: a bare dump


def _dumps_environment(tokens: list[str]) -> bool:
    """True for a command that prints environment variables.

    dlt resolves credentials from env vars as readily as from secrets.toml, so
    `env | grep -i key` leaks exactly what this guard exists to protect.
    """
    for index, token in enumerate(tokens):
        name = _basename(token)
        if name == "printenv":
            return True
        if name == "env" and _env_dumps(tokens[index + 1:]):
            return True
    return False


def _inline_code_blobs(tokens: list[str]) -> list[str]:
    """Tokens handed as inline code to an interpreter (`bash -c <blob>`).

    `bash -c "cat .env"` and `python3 -c "open('.env')"` hide the path inside
    one quoted token. Only blobs an interpreter is actually running are split
    open, so `git commit -m "fix .env loading"` stays allowed.
    """
    return [
        tokens[index + 1]
        for index, token in enumerate(tokens)
        if token in _CODE_FLAGS
        and index + 1 < len(tokens)
        and _basenames(tokens[:index]) & _INTERPRETERS
    ]


def _is_safe_secrets_cli(tokens: list[str]) -> bool:
    """True for `dlthub ai secrets {list,view-redacted,update-fragment}`.

    That command takes a secrets path as an argument by design and never
    prints an unredacted value — it is the route the deny message recommends,
    so matching its path argument would make the guard self-defeating. A guard
    that refuses its own escape hatch leaves the agent no sanctioned way to
    work with secrets, which is the state most likely to make it route around
    the guard. Anything else under `dlthub ai secrets` stays blocked: unknown
    subcommands fail closed.
    """
    # `sh -c '<command>'` — judge the command it actually runs. `all` so that
    # `sh -c 'dlthub ai secrets list && cat .env'` is not exempted wholesale.
    blobs = _inline_code_blobs(tokens)
    if blobs:
        inner = _command_segments(_tokenize(blobs[0]))
        return bool(inner) and all(_is_safe_secrets_cli(segment) for segment in inner)

    words = [_basename(token) for token in tokens]
    # skip any number of runners: `uv run dlthub ...`, `pipx run dlthub ...`
    start = next((i for i, word in enumerate(words) if word not in _CLI_RUNNERS), len(words))
    if words[start:start + 3] != ["dlthub", "ai", "secrets"]:
        return False
    for word in words[start + 3:]:
        if word.startswith("-"):
            continue  # a flag, or a flag's value; the subcommand comes first
        return word in _SAFE_CLI_SUBCOMMANDS
    return True  # bare `dlthub ai secrets` — prints usage


def _runs_guarded_code(tokens: list[str], cwd: str) -> bool:
    """True if an interpreter is handed inline code that names a guarded file."""
    for blob in _inline_code_blobs(tokens):
        inner = _command_segments(_tokenize(blob))
        if inner and all(_is_safe_secrets_cli(segment) for segment in inner):
            continue  # `sh -c 'dlthub ai secrets view-redacted --path ...'`
        if any(piece and _is_blocked_path(piece, cwd) for piece in _CODE_SPLIT.split(blob)):
            return True
    return False


def _read_deny_reason(command: str, cwd: str) -> str | None:
    """The deny message for what a shell command reads, or None to allow.

    Does NOT include the tamper check — use `_shell_deny_reason` for that.
    """
    tokens = _tokenize(command)

    # Phase 1 — whole-command checks, before splitting: an env dump or an
    # interpreter blob must not be laundered by a safe segment elsewhere in
    # the pipeline (this is why `<safe cli> | grep -i env` denies).
    if _dumps_environment(tokens) or _runs_guarded_code(tokens, cwd):
        return DENY_MESSAGE

    # Phase 2 — per segment, so a safe first command cannot vouch for a later one.
    for segment in _command_segments(tokens):
        if _is_safe_secrets_cli(segment):
            continue  # the sanctioned redacted-access route
        reads_in_bulk = bool(_basenames(segment) & _BULK_READERS)
        for token in segment:
            if any(char in token for char in _GLOB_CHARS):
                # judged by pattern and by expansion only: a glob token's
                # literal text is not a filename
                if _glob_is_blocked(token, cwd):
                    return DENY_MESSAGE
                continue
            if _is_blocked_path(token, cwd):
                return DENY_MESSAGE
            if reads_in_bulk and _is_secret_dir(token):
                return DIRECTORY_MESSAGE
    return None


def _tampers_with_guard(command: str) -> bool:
    """True if a shell command rewrites or deletes the guard or its config."""
    tokens = _tokenize(command)
    mutates = bool(_basenames(tokens) & _MUTATORS) or bool(set(tokens) & _WRITE_REDIRECTS)
    return mutates and any(_is_guard_path(token) for token in tokens)


def _shell_deny_reason(command: str, cwd: str) -> str | None:
    """Deny reason for a shell command: tamper check first, then guarded read.

    The single entry point for every dialect that hands this guard a shell
    command (Claude/Codex Bash, Cursor's beforeShellExecution), so the
    precedence cannot drift between them.
    """
    if _tampers_with_guard(command):
        return TAMPER_MESSAGE
    return _read_deny_reason(command, cwd)


# --- payload policy: what is this tool call doing? -------------------------


def _scan_values(value: object, cwd: str, depth: int = 0) -> bool:
    """Check every path-shaped string in an arbitrary tool payload.

    The fallback for tools with no dedicated branch — MCP servers, vendor
    payload drift, tools added after this script was written. _is_blocked_path
    matches a whole basename, so prose that merely mentions `.env` does not
    trip it.
    """
    if depth > _MAX_SCAN_DEPTH:
        # deeper than any real tool payload nests; bounds cost per tool call.
        # Note this is the one fail-OPEN path in the evaluator — a guarded
        # string nested deeper than this is allowed through.
        return False
    if isinstance(value, str):
        return _is_blocked_path(value, cwd)
    if isinstance(value, list):
        return any(_scan_values(item, cwd, depth + 1) for item in value)
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = key.lower() if isinstance(key, str) else ""
            if lowered in _PROSE_KEYS:
                continue  # prose, not a path: skips the whole subtree
            if lowered == "command" and isinstance(item, str):
                # read check only: tamper detection is not applied to commands
                # nested inside a generic payload
                if _read_deny_reason(item, cwd) is not None:
                    return True
                continue
            if _scan_values(item, cwd, depth + 1):
                return True
    return False


def _grep_paths(tool_input: dict) -> list:
    """Every path-like field of a Grep payload; shapes vary across agents."""
    raw = tool_input.get("paths")
    paths = [raw] if isinstance(raw, str) else list(raw) if isinstance(raw, list) else []
    return paths + [tool_input[key] for key in ("path", "file_path", "glob") if tool_input.get(key)]


def _tool_reason(payload: dict, cwd: str) -> str | None:
    """Deny message for a tool-shaped payload, or None to allow."""
    tool_name = payload.get("tool_name")
    name = tool_name.lower() if isinstance(tool_name, str) else ""

    # Before the tool_input check: the redacted-access tools take a secrets
    # path by design, whatever shape their payload arrives in.
    if name.endswith(_SAFE_TOOL_SUFFIXES):
        return None

    tool_input = payload.get("tool_input")
    if tool_input is None:
        tool_input = {}
    if not isinstance(tool_input, dict):
        # deliberate: a payload we cannot read is a payload we cannot clear,
        # so raise and let main() fail closed
        raise TypeError("tool_input is not an object")

    if name in _SHELL_TOOLS:
        return _shell_deny_reason(tool_input.get("command", ""), cwd)

    if name == "read":
        return DENY_MESSAGE if _is_blocked_path(tool_input.get("file_path", ""), cwd) else None

    if name == "grep":
        paths = _grep_paths(tool_input)
        return DENY_MESSAGE if any(_is_blocked_path(path, cwd) for path in paths) else None

    if name in _WRITE_TOOLS:
        # skip non-strings and empties: a malformed key is not a target
        targets = [tool_input.get(key) for key in ("file_path", "path", "notebook_path")]
        targets = [target for target in targets if isinstance(target, str) and target]
        if any(_is_guard_path(target) for target in targets):
            return TAMPER_MESSAGE  # checked first: tampering outranks reading
        if any(_is_blocked_path(target, cwd) for target in targets):
            return DENY_MESSAGE
        return None

    return DENY_MESSAGE if _scan_values(tool_input, cwd) else None


# --- entry point -----------------------------------------------------------


def deny_reason(payload: dict, cwd: str) -> str | None:
    """The deny message for any supported payload shape, or None to allow.

    Pure: no stdin, no exit codes, no output. Raises on a payload it cannot
    judge, which main() turns into a fail-closed deny.
    """
    event = payload.get("hook_event_name")
    if event in _CURSOR_FILE_EVENTS:
        return DENY_MESSAGE if _is_blocked_path(payload.get("file_path", ""), cwd) else None
    if event == "beforeShellExecution":
        return _shell_deny_reason(payload.get("command", ""), cwd)
    return _tool_reason(payload, cwd)


def _emit(reason: str | None, cursor: bool) -> None:
    """Answer in the caller's dialect. Claude Code / Codex spell allow as silence."""
    if cursor:
        response = (
            {"permission": "deny", "user_message": reason, "agent_message": reason}
            if reason
            else {"permission": "allow"}
        )
    elif reason:
        response = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    else:
        return
    print(json.dumps(response))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise TypeError("payload is not a JSON object")
    except Exception:
        # unidentifiable input: cannot name the operation, so let it proceed,
        # but never silently — traceback on stderr, exit 1 (a non-blocking
        # error; only exit 2 blocks). {"permission": "allow"} is a universal
        # proceed: cursor honors it, claude/codex ignore output that carries
        # no permissionDecision.
        traceback.print_exc()
        print(json.dumps({"permission": "allow"}))
        return 1

    try:
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            cwd = os.getcwd()
        reason = deny_reason(payload, cwd)
    except Exception:
        # identified a guarded operation but could not prove it safe
        # (unexpected field types, vendor payload drift): fail closed
        traceback.print_exc()
        reason = DENY_MESSAGE

    _emit(reason, payload.get("hook_event_name") in _CURSOR_EVENTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
