#!/usr/bin/env python3
"""Universal secrets-read guard for Claude Code, Codex, and Cursor hooks.

One stdlib-only file, no sibling imports — safe to copy anywhere. Detects the
calling agent from the stdin payload shape and answers in that agent's dialect:

- Claude Code / Codex (PreToolUse): stdin {"tool_name": ..., "tool_input": {...}},
  deny via {"hookSpecificOutput": {"permissionDecision": "deny", ...}} on stdout,
  allow via silence (exit 0, no output).
- Cursor (beforeReadFile / beforeShellExecution / beforeMCPExecution /
  beforeTabFileRead / preToolUse): deny via {"permission": "deny", ...},
  allow via {"permission": "allow"}.

Blocks reads of dlt secrets (secrets.toml, *.secrets.toml), dotenv files
(.env, .env.*, .envrc) and common credential files (.netrc, .pgpass,
service_account.json, ssh private keys, .aws/credentials). Placeholder
variants — example/template/sample — stay readable. Matching is
case-insensitive and ignores editor backup suffixes (.bak, ~, .save). A
symlink is judged by its real target too, so an innocuous-looking alias
pointing at a guarded file doesn't get a pass.

Shell commands are tokenized with shell punctuation split out, so `cat<.env`
and `cat .env|head` are caught. Glob tokens are expanded against the payload's
cwd, so `cat .dlt/*` is caught. `env`/`printenv` dumps are blocked because dlt
also reads credentials from environment variables.

Failure policy:
- stdin is not a JSON object: the operation cannot be identified, so allow —
  but loudly (traceback on stderr, {"permission": "allow"} on stdout, exit 1).
- the payload identifies a guarded operation but evaluating it raises: deny
  (fail closed) in the caller's dialect, traceback on stderr.

The deny channel is always the JSON on stdout, never the exit code: in both
Claude Code and Cursor only exit 2 blocks; exit 1 is a non-blocking error and
the action proceeds.

This is a deterrent, not a sandbox. Indirection (`cat $(echo .env)`, a Python
script that opens the file itself) and unscoped recursive readers
(`grep -r key .`) still get through — see README.md for the layers that do
close those.
"""

import glob as globlib
import json
import os
import re
import shlex
import sys
import traceback

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
_BULK_READERS = {
    "cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg",
    "find", "awk", "sed", "tar", "zip", "base64", "xxd", "od", "strings",
    "cp", "rsync", "tee",
}
_MUTATORS = {"rm", "mv", "cp", "sed", "tee", "truncate", "chmod", "dd", "ln", "shred", "unlink"}
# `bash -c "cat .env"` and `python3 -c "open('.env')"` hide the path inside one
# quoted token. Only split code blobs open when an interpreter is running them,
# so `git commit -m "fix .env loading"` stays allowed.
_INTERPRETERS = {
    "sh", "bash", "zsh", "dash", "ksh", "fish", "python", "python2", "python3",
    "node", "deno", "bun", "ruby", "perl", "php",
}
_CODE_FLAGS = {"-c", "-e", "--command", "--eval"}
_CODE_SPLIT = re.compile(r"""[\s"'(),;=\[\]{}]+""")
_REDIRECTS = {">", ">>"}
_OPERATORS = {"|", "||", "&&", ";", "&", ">", ">>", "<", "<<"}
_GLOB_CHARS = "*?["

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

# The redacted-access route this guard's own deny message tells the agent to
# use. Blocking it would leave the agent with no sanctioned way to work with
# secrets — the state most likely to make it route around the guard.
# Named by their trailing tool name so the MCP server can be called anything.
_SAFE_TOOL_SUFFIXES = ("secrets_list", "secrets_view_redacted", "secrets_update_fragment")
_SAFE_CLI_SUBCOMMANDS = {"list", "view-redacted", "update-fragment"}
_CLI_RUNNERS = {"uv", "uvx", "poetry", "pipx", "run", "exec", "--"}
_SEGMENT_BREAKS = {"|", "||", "&&", ";", "&", ">", ">>", "<", "<<"}

# Payload fields that carry prose rather than paths. Scanning them produces
# false denials (a Grep for the literal string "secrets.toml", a commit message
# that mentions .env) without adding protection.
_PROSE_KEYS = {
    "pattern", "content", "new_string", "old_string", "prompt", "description",
    "message", "body", "text", "query", "instructions", "explanation", "thought",
}

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


def _segments(path: str) -> list:
    return [seg for seg in path.replace("\\", "/").split("/") if seg not in ("", ".")]


def _strip_backup_suffixes(name: str) -> str:
    """`secrets.toml.bak` -> `secrets.toml`, `.env~` -> `.env`."""
    changed = True
    while changed:
        changed = False
        for suffix in _BACKUP_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                name = name[: -len(suffix)]
                changed = True
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


def _resolve(path: str, cwd: str) -> str:
    """Absolute path for `path`, resolved against `cwd` if relative.

    `os.path.join` already returns an absolute `path` unchanged, so no
    separate `isabs` branch is needed.
    """
    return os.path.join(cwd, os.path.expanduser(path))


def is_blocked_path(path: str, cwd: str = None) -> bool:
    """True if `path` names a dlt secrets, dotenv, or credential file.

    When `cwd` is given and `path` is itself a symlink, also judges what it
    resolves to: a symlink named `notes.txt` that points at `secrets.toml`
    is blocked by its real target, not just its innocent-looking alias.
    """
    if not isinstance(path, str):
        raise TypeError("path is not a string")

    segments = _segments(path)
    if not segments:
        return False
    # lowercase: macOS/Windows resolve SECRETS.TOML and secrets.toml to the same file
    name = _strip_backup_suffixes(segments[-1].lower())
    parent = segments[-2].lower() if len(segments) > 1 else ""
    if _is_blocked_name(name, parent):
        return True

    if cwd is not None:
        candidate = _resolve(path, cwd)
        if os.path.islink(candidate):
            # realpath is already absolute and fully resolved (chained
            # symlinks included), so re-check it as a plain name — no cwd
            # needed for a second hop.
            return is_blocked_path(os.path.realpath(candidate))

    return False


def is_secret_dir(path: str) -> bool:
    """True if `path` names a directory whose whole contents are secret."""
    segments = _segments(path)
    return bool(segments) and segments[-1].lower() in _SECRET_DIRS


def is_guard_path(path: str) -> bool:
    """True if `path` is this guard or the config that installs it."""
    segments = _segments(path)
    if not segments:
        return False
    name = segments[-1].lower()
    parent = segments[-2].lower() if len(segments) > 1 else ""
    return name in _GUARD_FILES or (parent, name) in _GUARD_CONFIGS


def _glob_is_blocked(token: str, cwd: str) -> bool:
    """True if a glob token can expand onto a guarded file."""
    normalized = token.replace("\\", "/")
    pattern = os.path.basename(normalized).lower()

    # `cat .dlt/*` names no guarded file but expands onto one
    if is_secret_dir(os.path.dirname(normalized)):
        return True

    # Filesystem-independent: the pattern itself is aimed at guarded names, so
    # it stays blocked even when the file does not exist yet. Restricted to
    # secrets-shaped patterns — a bare `*.toml` or `*` is judged by expansion
    # alone, or `cat *.toml` in a project root would be refused.
    if pattern.startswith(".env") or "secret" in pattern or "credential" in pattern:
        return True

    expanded = _resolve(token, cwd)
    matches = globlib.glob(expanded)
    return any(is_blocked_path(match, cwd) or is_secret_dir(match) for match in matches)


def _tokenize(command: str) -> list:
    """Split a shell command, keeping punctuation as separate tokens.

    punctuation_chars is what makes `cat<.env` and `cat .env|head` visible:
    plain shlex.split returns them as single glued tokens whose basename
    matches nothing.
    """
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        # Broken quoting — bash would reject it too, but strip the quote
        # characters so a half-quoted path still matches.
        return [token.strip("\"'") for token in command.split()]


def _basenames(tokens: list) -> set:
    return {os.path.basename(token.replace("\\", "/")).lower() for token in tokens}


def _dumps_environment(tokens: list) -> bool:
    """True for a command that prints environment variables.

    dlt resolves credentials from env vars as readily as from secrets.toml, so
    `env | grep -i key` leaks exactly what this guard exists to protect.
    """
    for index, token in enumerate(tokens):
        name = os.path.basename(token.replace("\\", "/")).lower()
        if name == "printenv":
            return True
        if name != "env":
            continue
        # `env FOO=bar cmd` and `env -u X cmd` run a command; a dump has no
        # operand of its own before the next shell operator.
        for rest in tokens[index + 1:]:
            if rest in _OPERATORS:
                return True
            if not rest.startswith("-") and "=" not in rest:
                break  # an operand: this is `env <cmd>`, not a dump
        else:
            return True
    return False


def _is_safe_secrets_cli(tokens: list) -> bool:
    """True for `dlthub ai secrets {list,view-redacted,update-fragment}`.

    That command takes a secrets path as an argument by design and never
    prints an unredacted value — it is the route the deny message recommends,
    so matching its path argument would make the guard self-defeating.
    Anything else under `dlthub ai secrets` stays blocked: unknown
    subcommands fail closed.
    """
    # `sh -c '<command>'` — judge the command it actually runs. `all` so that
    # `sh -c 'dlthub ai secrets list && cat .env'` is not exempted wholesale.
    for position, token in enumerate(tokens):
        if token in _CODE_FLAGS and position + 1 < len(tokens):
            if _basenames(tokens[:position]) & _INTERPRETERS:
                inner = _split_segments(_tokenize(tokens[position + 1]))
                return bool(inner) and all(_is_safe_secrets_cli(seg) for seg in inner)

    words = [os.path.basename(token.replace("\\", "/")).lower() for token in tokens]
    index = 0
    while index < len(words) and words[index] in _CLI_RUNNERS:
        index += 1
    if words[index:index + 3] != ["dlthub", "ai", "secrets"]:
        return False
    for word in words[index + 3:]:
        if word.startswith("-"):
            continue  # a flag, or a flag's value; the subcommand comes first
        return word in _SAFE_CLI_SUBCOMMANDS
    return True  # bare `dlthub ai secrets` — prints usage


def _split_segments(tokens: list) -> list:
    """Split a token list on shell operators, so each command is judged alone.

    Without this, `dlthub ai secrets list && cat .env` would inherit the safe
    verdict of its first command.
    """
    segments, current = [], []
    for token in tokens:
        if token in _SEGMENT_BREAKS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _runs_guarded_code(tokens: list, cwd: str) -> bool:
    """True if an interpreter is handed inline code that names a guarded file."""
    for index, token in enumerate(tokens):
        if token not in _CODE_FLAGS or index + 1 >= len(tokens):
            continue
        if not (_basenames(tokens[:index]) & _INTERPRETERS):
            continue
        blob = tokens[index + 1]
        inner = _split_segments(_tokenize(blob))
        if inner and all(_is_safe_secrets_cli(seg) for seg in inner):
            continue  # `sh -c 'dlthub ai secrets view-redacted --path ...'`
        for piece in _CODE_SPLIT.split(blob):
            if piece and is_blocked_path(piece, cwd):
                return True
    return False


def command_deny_reason(command: str, cwd: str):
    """The deny message for a shell command, or None to allow."""
    # shlex on a non-string silently reads stdin on older pythons instead of
    # raising; force a raise so the caller fails closed on a malformed payload
    if not isinstance(command, str):
        raise TypeError("command is not a string")

    tokens = _tokenize(command)
    if _dumps_environment(tokens) or _runs_guarded_code(tokens, cwd):
        return DENY_MESSAGE

    for segment in _split_segments(tokens):
        if _is_safe_secrets_cli(segment):
            continue  # the sanctioned redacted-access route
        reads_in_bulk = bool(_basenames(segment) & _BULK_READERS)
        for token in segment:
            if any(char in token for char in _GLOB_CHARS):
                if _glob_is_blocked(token, cwd):
                    return DENY_MESSAGE
                continue
            if is_blocked_path(token, cwd):
                return DENY_MESSAGE
            if reads_in_bulk and is_secret_dir(token):
                return DIRECTORY_MESSAGE
    return None


def command_is_blocked(command: str, cwd: str) -> bool:
    """True if a shell command reads a guarded file or dumps the environment."""
    return command_deny_reason(command, cwd) is not None


def command_tampers_with_guard(command: str) -> bool:
    """True if a shell command rewrites or deletes the guard or its config."""
    tokens = _tokenize(command)
    mutates = bool(_basenames(tokens) & _MUTATORS) or bool(set(tokens) & _REDIRECTS)
    return mutates and any(is_guard_path(token) for token in tokens)


def _scan_values(value, cwd: str, depth: int = 0) -> bool:
    """Check every path-shaped string in an arbitrary tool payload.

    The fallback for tools with no dedicated branch — MCP servers, vendor
    payload drift, tools added after this script was written. is_blocked_path
    matches a whole basename, so prose that merely mentions `.env` does not
    trip it.
    """
    if depth > 6:
        return False
    if isinstance(value, str):
        return is_blocked_path(value, cwd)
    if isinstance(value, list):
        return any(_scan_values(item, cwd, depth + 1) for item in value)
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _PROSE_KEYS:
                continue
            if isinstance(key, str) and key.lower() == "command" and isinstance(item, str):
                if command_is_blocked(item, cwd):
                    return True
                continue
            if _scan_values(item, cwd, depth + 1):
                return True
    return False


def _tool_reason(payload: dict, cwd: str):
    """Deny message for a tool-shaped payload, or None to allow."""
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input")
    if tool_input is None:
        tool_input = {}
    name = tool_name.lower() if isinstance(tool_name, str) else ""

    if name.endswith(_SAFE_TOOL_SUFFIXES):
        return None  # the redacted-access tools take a secrets path by design

    if name in ("bash", "shell", "powershell"):
        command = tool_input.get("command", "")
        if command_tampers_with_guard(command):
            return TAMPER_MESSAGE
        return command_deny_reason(command, cwd)

    if name == "read":
        return DENY_MESSAGE if is_blocked_path(tool_input.get("file_path", ""), cwd) else None

    if name == "grep":
        raw_paths = tool_input.get("paths")
        if isinstance(raw_paths, str):
            paths = [raw_paths]
        elif isinstance(raw_paths, list):
            paths = list(raw_paths)
        else:
            paths = []
        # grep payload shapes vary across agents; check every path-like field
        for key in ("path", "file_path", "glob"):
            if tool_input.get(key):
                paths.append(tool_input[key])
        return DENY_MESSAGE if any(is_blocked_path(path, cwd) for path in paths) else None

    if name in _WRITE_TOOLS:
        targets = [tool_input.get(key, "") for key in ("file_path", "path", "notebook_path")]
        if any(isinstance(t, str) and is_guard_path(t) for t in targets if t):
            return TAMPER_MESSAGE
        if any(isinstance(t, str) and is_blocked_path(t, cwd) for t in targets if t):
            return DENY_MESSAGE
        return None

    return DENY_MESSAGE if _scan_values(tool_input, cwd) else None


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

    event = payload.get("hook_event_name")
    is_cursor = event in _CURSOR_EVENTS

    try:
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            cwd = os.getcwd()

        if event in _CURSOR_FILE_EVENTS:
            reason = DENY_MESSAGE if is_blocked_path(payload.get("file_path", ""), cwd) else None
        elif event == "beforeShellExecution":
            command = payload.get("command", "")
            if command_tampers_with_guard(command):
                reason = TAMPER_MESSAGE
            else:
                reason = command_deny_reason(command, cwd)
        else:
            reason = _tool_reason(payload, cwd)
    except Exception:
        # identified a guarded operation but could not prove it safe
        # (unexpected field types, vendor payload drift): fail closed
        traceback.print_exc()
        reason = DENY_MESSAGE

    if is_cursor:
        if reason:
            print(json.dumps({"permission": "deny", "user_message": reason, "agent_message": reason}))
        else:
            print(json.dumps({"permission": "allow"}))
    elif reason:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
