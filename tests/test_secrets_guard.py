"""Tests for workbench/init/hooks/secrets_guard.py.

Two tiers, because the guard has two contracts:

- **Decisions** (most of the file) exercise `deny_reason()` in process and
  assert the *exact* message constant. Table-driven, ~20ms for the lot, so
  coverage is limited by imagination rather than by subprocess cost. Asserting
  the constant — not merely "something was returned" — is what stops a refactor
  from silently swapping DENY for TAMPER, or denying by crashing.
- **The process contract** (`ProcessContract` and below) runs the guard as a
  subprocess exactly the way the agents do: payload on stdin, decision read
  from stdout JSON plus the exit code. That is the right altitude for the two
  output dialects, allow-is-silence, and the fail-open/fail-closed split.

Both tiers share one real temp workspace so glob expansion and symlink
resolution have something to resolve against.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "workbench" / "init" / "hooks" / "secrets_guard.py"


def _load_guard():
    """Import the guard as a module. It guards `__main__`, so this is safe."""
    spec = importlib.util.spec_from_file_location("secrets_guard", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()

# The four verdicts, named so a table row reads as its own assertion.
ALLOW = None
DENY = guard.DENY_MESSAGE
DIRECTORY = guard.DIRECTORY_MESSAGE
TAMPER = guard.TAMPER_MESSAGE

WORKSPACE: Path


def setUpModule():
    """One workspace for every test; nothing below mutates it."""
    global WORKSPACE
    WORKSPACE = Path(tempfile.mkdtemp(prefix="dlt-guard-test-"))
    for directory in (".dlt", ".claude", ".codex", ".ssh", ".gnupg", "src", ".agents/hooks"):
        (WORKSPACE / directory).mkdir(parents=True)
    for name, content in [
        (".dlt/secrets.toml", "password='REAL'\n"),
        (".dlt/dev.secrets.toml", "password='REAL'\n"),
        (".dlt/example.secrets.toml", "password='<set me>'\n"),
        (".dlt/config.toml", "[runtime]\n"),
        (".env", "API_KEY=REAL\n"),
        (".env.example", "API_KEY=\n"),
        (".netrc", "machine x login y\n"),
        (".claude/settings.json", "{}\n"),
        (".claude/CLAUDE.md", "# project\n"),
        (".codex/config.toml", "model = 'x'\n"),
        (".ssh/id_ed25519", "KEY\n"),
        (".ssh/id_ed25519.pub", "PUB\n"),
        (".agents/hooks/secrets_guard.py", "# the guard\n"),
        ("pyproject.toml", "[project]\n"),
        ("README.md", "# readme\n"),
        ("src/pipeline.py", "import dlt\n"),
    ]:
        (WORKSPACE / name).write_text(content)
    # a link named innocently, pointing at a secret; and one at a secret *dir*
    (WORKSPACE / "notes.txt").symlink_to(WORKSPACE / ".dlt" / "secrets.toml")
    (WORKSPACE / "readme-link.md").symlink_to(WORKSPACE / "pyproject.toml")
    (WORKSPACE / "dlink").symlink_to(WORKSPACE / ".dlt")


def tearDownModule():
    shutil.rmtree(WORKSPACE, ignore_errors=True)


class DecisionTestCase(unittest.TestCase):
    """Tier 1: `deny_reason()` in process, asserting the exact message."""

    def assert_decisions(self, cases, tool=None):
        """Each case is (expected_message_or_ALLOW, tool_input-or-command)."""
        for expected, payload in cases:
            with self.subTest(payload=payload):
                if tool is not None:
                    full = {"tool_name": tool, "tool_input": payload}
                else:
                    full = payload
                self.assertEqual(guard.deny_reason(full, str(WORKSPACE)), expected)

    def assert_reads(self, cases):
        self.assert_decisions([(e, {"file_path": p}) for e, p in cases], tool="Read")

    def assert_commands(self, cases):
        self.assert_decisions([(e, {"command": c}) for e, c in cases], tool="Bash")


class BlockedNames(DecisionTestCase):
    """Which basenames are guarded, at any directory depth."""

    def test_dlt_secrets(self):
        self.assert_reads([
            (DENY, ".dlt/secrets.toml"),
            (DENY, "secrets.toml"),
            (DENY, ".dlt/dev.secrets.toml"),
            (DENY, "deep/nested/prod.secrets.toml"),
            (ALLOW, ".dlt/example.secrets.toml"),
            (ALLOW, ".dlt/template.secrets.toml"),
            (ALLOW, ".dlt/sample.secrets.toml"),
            # the placeholder exemption is the whole stem, not a suffix
            (DENY, ".dlt/dev.example.secrets.toml"),
            (ALLOW, ".dlt/config.toml"),
        ])

    def test_dotenv(self):
        self.assert_reads([
            (DENY, ".env"),
            (DENY, ".env.production"),
            (DENY, ".env.local"),
            (DENY, ".envrc"),
            (ALLOW, ".env.example"),
            (ALLOW, ".env.template"),
            (ALLOW, ".env.sample"),
            (ALLOW, ".environment"),
            (ALLOW, ".envy"),
            (ALLOW, "environment.ts"),
            (ALLOW, "myenv"),
        ])

    def test_credentials(self):
        self.assert_reads([
            (DENY, "~/.netrc"),
            (DENY, "~/_netrc"),
            (DENY, "~/.pgpass"),
            (DENY, "~/.pypirc"),
            (DENY, "service_account.json"),
            (DENY, "application_default_credentials.json"),
            (DENY, "~/.ssh/id_rsa"),
            (DENY, "~/.ssh/id_dsa"),
            (DENY, "~/.ssh/id_ecdsa"),
            (DENY, "~/.ssh/id_ed25519"),
            (DENY, "~/.aws/credentials"),
            (DENY, "~/.azure/credentials"),
            (ALLOW, "~/.ssh/id_ed25519.pub"),
            (ALLOW, "id_rsa.pub"),
            # the bare name is too common to block; only inside .aws/.azure
            (ALLOW, "credentials"),
            (ALLOW, "aws/credentials"),
        ])

    def test_case_insensitive(self):
        self.assert_reads([
            (DENY, ".dlt/SECRETS.TOML"),
            (DENY, ".dlt/SeCrEtS.ToMl"),
            (DENY, ".ENV"),
        ])

    def test_backup_suffixes_are_stripped(self):
        self.assert_reads([
            (DENY, ".dlt/secrets.toml.bak"),
            (DENY, "secrets.toml.orig"),
            (DENY, "secrets.toml.save"),
            (DENY, ".env~"),
            (DENY, ".env.swp"),
            (DENY, ".env.bak.bak"),
            # needs the loop: one pass leaves secrets.toml.bak, which no rule matches
            (DENY, "secrets.toml.bak.bak"),
            (DENY, "secrets.toml.tmp.old"),
            (ALLOW, ".env.example.bak"),
            # a name that IS a suffix must not strip to "" and vanish
            (ALLOW, ".bak"),
            (ALLOW, "~"),
        ])

    def test_windows_separators(self):
        self.assert_reads([(DENY, r".dlt\secrets.toml"), (DENY, r"C:\proj\.env")])

    def test_empty_and_degenerate_paths(self):
        self.assert_reads([(ALLOW, ""), (ALLOW, "."), (ALLOW, "/"), (ALLOW, "..")])

    def test_symlinks_are_judged_by_target(self):
        self.assert_reads([
            (DENY, "notes.txt"),          # -> .dlt/secrets.toml
            (ALLOW, "readme-link.md"),    # -> pyproject.toml
        ])


class ShellDecisions(DecisionTestCase):
    """What a Bash command earns, by exact message."""

    def test_plain_reads(self):
        self.assert_commands([
            (DENY, "cat .dlt/secrets.toml"),
            (DENY, "cat .env"),
            (DENY, "cat ./.env"),
            (DENY, "cat 'a b/.env'"),
            (DENY, 'cat ".env"'),
            (DENY, "cat notes.txt"),
            (ALLOW, "cat README.md"),
            (ALLOW, "cat .dlt/config.toml"),
            (ALLOW, "cat readme-link.md"),
        ])

    def test_punctuation_is_tokenized_out(self):
        # shlex.split alone returns 'cat<.env' as one token, matching nothing
        self.assert_commands([
            (DENY, "cat<.env"),
            (DENY, "cat .env|head"),
            (DENY, "cat .env>out"),
            (DENY, "cat .env;echo hi"),
            (DENY, "cat a && cat .env"),
        ])

    def test_globs(self):
        self.assert_commands([
            # arm 1: the directory it points at, even when nothing matches
            (DENY, "cat .gnupg/nothing*"),
            (DENY, "cat .dlt/*"),
            (DENY, "cat .dlt/*.toml"),
            # arm 2: the shape of the pattern itself
            (DENY, "cat .env*"),
            (DENY, "cat *secret*"),
            (ALLOW, "cat *.toml"),
            (ALLOW, "cat src/*.py"),
        ])

    def test_glob_expansion_is_the_last_arm(self):
        """A pattern neither secrets-shaped nor in a secret dir, but which
        expands onto a guarded file right now — the only arm that reads disk."""
        self.assert_commands([(DENY, "cat .netr*"), (ALLOW, "cat READ*.md")])

    def test_bulk_readers_on_a_secret_directory(self):
        self.assert_commands([
            (DIRECTORY, "grep -r password .dlt/"),
            (DIRECTORY, "grep -rn destination .dlt/"),
            (DIRECTORY, "tar cf - .dlt | base64"),
            (DIRECTORY, "rsync -a .ssh/ /tmp/"),
            # names only, no contents
            (ALLOW, "ls -la .dlt"),
            (ALLOW, "ls .ssh"),
        ])

    def test_directory_message_points_at_the_alternative(self):
        self.assertIn("config.toml", DIRECTORY)

    def test_inline_interpreter_code(self):
        self.assert_commands([
            (DENY, "bash -c 'cat .env'"),
            (DENY, 'sh -c "cat .env"'),
            (DENY, "python3 -c \"print(open('.env').read())\""),
            (DENY, "node -e \"require('fs').readFileSync('.env')\""),
            # only interpreters get their blob split open
            (ALLOW, "git commit -m 'fix .env loading'"),
            (ALLOW, 'git commit -m "read secrets.toml"'),
            (ALLOW, "python3 -c \"print(open('README.md').read())\""),
        ])

    def test_environment_dumps(self):
        self.assert_commands([
            (DENY, "env"),
            (DENY, "/usr/bin/env"),
            (DENY, "printenv"),
            (DENY, "printenv | grep -i key"),
            (DENY, "env | grep KEY"),
            # the prefix form runs a command instead of printing
            (ALLOW, "env FOO=1 python src/pipeline.py"),
            (ALLOW, "env -u PATH ls"),
            (ALLOW, "env -i ls"),
            (ALLOW, "/usr/bin/env python3 x.py"),
        ])

    def test_a_grep_pattern_is_not_a_path(self):
        """`grep secrets.toml src/` searches FOR the string; it reads nothing.

        The Grep *tool* already skips its `pattern` field; a Bash `grep` had
        its pattern checked as though it were a filename.
        """
        self.assert_commands([
            (ALLOW, "grep secrets.toml src/"),
            (ALLOW, "grep -rn .env src/"),
            (ALLOW, "rg secrets.toml"),
            # the operands after the pattern are still paths
            (DENY, "grep api_key .env"),
            (DENY, "grep -rn api_key .env src/"),
            # -e/-f supply the pattern, so every positional is a file and
            # none may be skipped — without this the first one is a free read.
            # The attached spellings matter most: there the FILE is the first
            # positional, so skipping it hands over the read.
            (DENY, "grep -e api_key .env"),
            (DENY, "grep -f patterns.txt .env"),
            (DENY, "grep -eapi_key .env"),
            (DENY, "grep -fpat.txt .env"),
            (DENY, "grep --regexp=api_key .env"),
        ])

    def test_malformed_quoting_still_matches(self):
        self.assert_commands([(DENY, 'cat "unterminated .env'), (ALLOW, "cat 'a")])

    def test_empty_command(self):
        self.assert_commands([(ALLOW, ""), (ALLOW, "   ")])


class MultiLineCommands(DecisionTestCase):
    """A newline ends a command, so an exempt line cannot vouch for the next.

    Regression: shlex treats "\\n" as plain whitespace, which collapsed a
    multi-line command into one segment and let the safe-CLI exemption launder
    every line after the first.
    """

    def test_later_lines_are_judged_on_their_own(self):
        self.assert_commands([
            (DENY, "dlthub ai secrets list\ncat .env"),
            (DENY, "echo hi\ndlthub ai secrets list\ncat .dlt/secrets.toml"),
            (DENY, "cd src\ncat ../.env"),
        ])

    def test_a_bare_env_line_is_still_a_dump(self):
        self.assert_commands([(DENY, "cd src\nenv"), (DENY, "env\nls")])

    def test_every_line_safe_stays_allowed(self):
        self.assert_commands([
            (ALLOW, "cd src\nmake all\nls -la"),
            (ALLOW, "dlthub ai secrets list\n"
                    "dlthub ai secrets view-redacted --path .dlt/secrets.toml"),
        ])

    def test_a_backslash_continues_the_line(self):
        """`cat \\<newline>.env` is one command in bash, reading `.env`.

        shlex raises on a line ending in a backslash, so the continuation took
        the same retry path as an unbalanced quote and glued a literal newline
        onto the next word — producing a token that matched nothing.
        """
        self.assert_commands([
            (DENY, "cat \\\n.env"),
            # the continuation is one command, so `grep` still owns `.dlt/`
            (DIRECTORY, "grep -r key \\\n.dlt/"),
        ])

    def test_a_newline_inside_quotes_is_not_a_separator(self):
        # the quote continues the word, so this is one token, not a path
        self.assert_commands([
            (ALLOW, 'git commit -m "fix\n.env loading"'),
            (ALLOW, 'echo "line1\nline2"'),
        ])


class SecretDirSymlinks(DecisionTestCase):
    """A link to a secret directory leaks it under a harmless name."""

    def test_bulk_read_through_a_directory_symlink(self):
        self.assert_commands([
            (DIRECTORY, "grep -r key dlink"),
            (DIRECTORY, "tar cf - dlink"),
        ])

    def test_a_trailing_slash_does_not_skip_the_hop(self):
        """os.path.islink("d/") is False even when `d` is a link, so the
        resolved path has to be normalized before the check."""
        self.assert_commands([
            (DIRECTORY, "grep -r key dlink/"),
            (DIRECTORY, "tar -cf o.tar dlink/"),
        ])

    def test_listing_through_the_link_is_still_fine(self):
        self.assert_commands([(ALLOW, "ls dlink")])


class EscapeHatch(DecisionTestCase):
    """The route the deny message recommends must not itself be blocked.

    A guard that refuses its own escape hatch leaves the agent with no
    sanctioned way to work with secrets, which is the state most likely to
    make it route around the guard.
    """

    def test_sanctioned_cli(self):
        self.assert_commands([
            (ALLOW, "dlthub ai secrets list"),
            (ALLOW, "dlthub ai secrets"),
            (ALLOW, "dlthub ai secrets view-redacted --path .dlt/secrets.toml"),
            (ALLOW, "dlthub ai secrets update-fragment --path .dlt/secrets.toml '[x]'"),
            (ALLOW, "uv run dlthub ai secrets view-redacted --path .dlt/dev.secrets.toml"),
            (ALLOW, "uvx dlthub ai secrets list"),
            (ALLOW, "poetry run dlthub ai secrets list"),
            (ALLOW, "dlthub ai secrets view-redacted --path .dlt/secrets.toml | head -20"),
            (ALLOW, "bash -c 'dlthub ai secrets view-redacted --path .dlt/secrets.toml'"),
        ])

    def test_the_exemption_is_not_a_hole(self):
        self.assert_commands([
            # unknown subcommands fail closed
            (DENY, "dlthub ai secrets export --path .dlt/secrets.toml"),
            # a safe first command cannot vouch for a later one
            (DENY, "dlthub ai secrets list && cat .env"),
            (DENY, "dlthub ai secrets view-redacted --path .dlt/secrets.toml; cat .env"),
            (DENY, "sh -c 'dlthub ai secrets list && cat .env'"),
            # nor for a subshell sharing its segment
            (DENY, "dlthub ai secrets list $(cat .env)"),
            (DENY, "dlthub ai secrets view-redacted --path .dlt/secrets.toml $(cat .env)"),
        ])

    def test_redacted_mcp_tools(self):
        for tool in (
            "mcp__dlt-workspace-mcp__secrets_view_redacted",
            "mcp__anything__secrets_update_fragment",
            "mcp__x__secrets_list",
        ):
            with self.subTest(tool=tool):
                payload = {"tool_name": tool, "tool_input": {"path": ".dlt/secrets.toml"}}
                self.assertIsNone(guard.deny_reason(payload, str(WORKSPACE)))

    def test_a_near_miss_on_the_suffix_is_not_exempt(self):
        payload = {"tool_name": "mcp__x__secrets_listing", "tool_input": {"path": ".env"}}
        self.assertEqual(guard.deny_reason(payload, str(WORKSPACE)), DENY)


class Tampering(DecisionTestCase):
    """Rewriting the guard, or the config that installs it, is refused."""

    def test_shell_mutations_of_guard_files(self):
        self.assert_commands([
            (TAMPER, "rm .agents/hooks/secrets_guard.py"),
            (TAMPER, "sed -i '' 's/secrets_guard//' .claude/settings.json"),
            (TAMPER, "mv .claude/settings.json /tmp/"),
            (TAMPER, "echo '{}' > .claude/settings.json"),
            (TAMPER, "chmod 000 .cursor/hooks.json"),
            (TAMPER, "ln -sf /dev/null .codex/hooks.json"),
        ])

    def test_shell_mutations_of_guard_directories(self):
        self.assert_commands([
            (TAMPER, "rm -rf .claude"),
            (TAMPER, "mv .claude .claude.off"),
            (TAMPER, "chmod -R 000 .claude"),
            (TAMPER, "rm -r .agents/hooks"),
            (TAMPER, "find .claude -delete"),
            (TAMPER, "find . -name secrets_guard.py -exec rm {} ;"),
        ])

    def test_interpreter_one_liners(self):
        self.assert_commands([
            (TAMPER, "python3 -c \"import shutil;shutil.rmtree('.claude')\""),
            (TAMPER, "python3 -c \"import os;os.unlink('.agents/hooks/secrets_guard.py')\""),
        ])

    def test_write_tools(self):
        self.assert_decisions([
            (TAMPER, {"file_path": ".agents/hooks/secrets_guard.py", "content": "x"}),
            (TAMPER, {"file_path": ".claude/settings.json", "content": "x"}),
        ], tool="Write")

    def test_reading_the_config_is_fine(self):
        self.assert_commands([
            (ALLOW, "cat .claude/settings.json"),
            (ALLOW, "cat .codex/hooks.json"),
        ])

    def test_unrelated_files_inside_a_guard_directory(self):
        # only the directory itself is the guarded target
        self.assert_commands([
            (ALLOW, "rm .claude/CLAUDE.md"),
            (ALLOW, "cat .claude/CLAUDE.md"),
        ])

    def test_the_check_is_per_segment(self):
        """A mutator in one command must not vouch for a guard path in another.

        Widening guard paths to whole directories made this reachable: every
        one of these was denied as tampering until the check was segmented.
        """
        self.assert_commands([
            (ALLOW, "rm -rf node_modules && ls .claude"),
            (ALLOW, "echo hi > out.txt && ls .agents"),
            (ALLOW, "rm -rf build\nls .cursor"),
            (ALLOW, "rsync -a --delete src/ /tmp/d/ && ls .claude"),
        ])

    def test_a_redirect_is_judged_by_its_target(self):
        # `>` is itself a segment break, so the target is checked by adjacency
        self.assert_commands([
            (TAMPER, "echo '{}' > .claude/settings.json"),
            (ALLOW, "ls .claude > out.txt"),
            (ALLOW, "grep -r foo .claude > out.txt"),
        ])

    def test_guard_directories_are_protected_only_against_destruction(self):
        """`cp`/`tee` name a guard directory without disabling anything.

        Guard *files* are protected against any mutation; directories only
        against being destroyed or renamed. Refusing the rest denied ordinary
        work in a repo that ships `.claude/` content.
        """
        self.assert_commands([
            (ALLOW, "cp -r .claude /tmp/backup"),
            (ALLOW, "cp README.md .claude/"),
            (ALLOW, "tar -czf backup.tgz .claude"),
            (ALLOW, "git add .claude"),
        ])

    def test_codex_config_toml_is_deliberately_unguarded(self):
        # Codex hooks live in .codex/hooks.json (openai/codex#17532), so
        # config.toml carries no guard registration to protect
        self.assert_commands([(ALLOW, "sed -i '' 's/a/b/' .codex/config.toml")])
        self.assert_decisions(
            [(ALLOW, {"file_path": ".codex/config.toml", "old_string": "a", "new_string": "b"})],
            tool="Edit",
        )

    def test_codex_hooks_json_is_guarded(self):
        self.assert_decisions(
            [(TAMPER, {"file_path": ".codex/hooks.json", "old_string": "a", "new_string": "b"})],
            tool="Edit",
        )


class ToolDecisions(DecisionTestCase):
    """Per-tool branches: Read, Grep, the write tools, and the generic scan."""

    def test_grep_path_shapes(self):
        self.assert_decisions([
            (DENY, {"paths": ".dlt/secrets.toml"}),
            (DENY, {"paths": ["src/", ".env.production"]}),
            (DENY, {"glob": "secrets.toml"}),
            (DENY, {"path": ".env"}),
            # Cursor's Claude-compatible Grep sends file_path, not path
            (DENY, {"file_path": ".env"}),
            (ALLOW, {"file_path": "README.md"}),
            (ALLOW, {"paths": ["src/"], "path": "README.md"}),
            (ALLOW, {"paths": 7}),
            (ALLOW, {}),
            # searching *for the string* reveals nothing
            (ALLOW, {"pattern": "secrets.toml", "path": "src"}),
        ], tool="Grep")

    def test_write_tools(self):
        for tool in ("Write", "Edit", "MultiEdit", "apply_patch", "NotebookEdit"):
            with self.subTest(tool=tool):
                self.assert_decisions([(DENY, {"file_path": ".env"})], tool=tool)
        self.assert_decisions([(ALLOW, {"file_path": "src/pipeline.py"})], tool="Write")
        self.assert_decisions([(DENY, {"notebook_path": ".env"})], tool="NotebookEdit")

    def test_shell_aliases(self):
        for tool in ("Bash", "shell", "powershell"):
            with self.subTest(tool=tool):
                self.assert_decisions([(DENY, {"command": "cat .env"})], tool=tool)

    def test_glob_tool_is_not_covered(self):
        # Glob lists filenames only; it reveals no content
        self.assert_decisions([(ALLOW, {"pattern": "**/.env"})], tool="Glob")

    def test_generic_scan_of_unknown_tools(self):
        self.assert_decisions([
            (DENY, {"path": ".dlt/secrets.toml"}),
            (DENY, {"a": {"b": {"c": [".env"]}}}),
            (DENY, {"command": "cat .env"}),
            (TAMPER, {"command": "rm .agents/hooks/secrets_guard.py"}),
            (ALLOW, {"command": "ls"}),
            # prose fields are skipped: a mention is not an access
            (ALLOW, {"query": "check .env handling"}),
            (ALLOW, {"content": ".env"}),
        ], tool="mcp__filesystem__read_file")

    def test_generic_scan_covers_any_field_name(self):
        """A shell-capable tool naming its field anything but `command` is still caught."""
        self.assert_decisions([
            (DENY, {"cmd": "cat .env"}),
            (DENY, {"shell_command": "cat .dlt/secrets.toml"}),
            (DENY, {"script": "cat .env"}),
            (TAMPER, {"exec": "rm -rf .claude"}),
            (ALLOW, {"cmd": "ls -la"}),
        ], tool="mcp__filesystem__exec")

    def test_generic_scan_depth_cap(self):
        deep = {"a": {"b": {"c": {"d": {"e": ".env"}}}}}
        self.assert_decisions([(DENY, deep)], tool="mcp__x__y")
        # deeper than any real payload nests; the one fail-open path
        deeper = {"a": {"b": {"c": {"d": {"e": {"f": {"g": ".env"}}}}}}}
        self.assert_decisions([(ALLOW, deeper)], tool="mcp__x__y")


class FailClosed(DecisionTestCase):
    """A payload that cannot be judged must raise, so main() denies."""

    def assert_raises_on(self, payload):
        with self.assertRaises(Exception):
            guard.deny_reason(payload, str(WORKSPACE))

    def test_non_string_command(self):
        self.assert_raises_on({"tool_name": "Bash", "tool_input": {"command": None}})
        self.assert_raises_on({"tool_name": "Bash", "tool_input": {"command": 7}})

    def test_non_string_path(self):
        self.assert_raises_on({"tool_name": "Read", "tool_input": {"file_path": 7}})

    def test_non_dict_tool_input(self):
        self.assert_raises_on({"tool_name": "Read", "tool_input": "not a dict"})
        self.assert_raises_on({"tool_name": "Read", "tool_input": [1, 2]})

    def test_tolerated_shapes_do_not_raise(self):
        # a missing or null tool_input is a shape we can clear, not one we can't
        self.assertIsNone(guard.deny_reason({"tool_name": "Read"}, str(WORKSPACE)))
        self.assertIsNone(
            guard.deny_reason({"tool_name": "Read", "tool_input": None}, str(WORKSPACE))
        )


# --- Tier 2: the process contract ------------------------------------------


def run_guard(stdin_text, cwd=None):
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class ProcessContract(unittest.TestCase):
    """Stdin in, JSON out — the contract the three agents actually rely on."""

    def claude(self, tool_name, tool_input):
        return run_guard(json.dumps({
            "hook_event_name": "PreToolUse",
            "cwd": str(WORKSPACE),
            "tool_name": tool_name,
            "tool_input": tool_input,
        }))

    def cursor(self, event, **fields):
        return run_guard(json.dumps({
            "hook_event_name": event, "cwd": str(WORKSPACE), **fields
        }))

    def assert_claude(self, result, reason=ALLOW):
        """Claude/Codex: deny is JSON on stdout, allow is silence, never exit 2."""
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", "guard crashed; a deny must be a decision")
        if reason is ALLOW:
            self.assertEqual(result.stdout, "")
            return
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertEqual(decision["permissionDecisionReason"], reason)

    def assert_cursor(self, result, reason=ALLOW):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "", "guard crashed; a deny must be a decision")
        out = json.loads(result.stdout)
        if reason is ALLOW:
            self.assertEqual(out, {"permission": "allow"})
            return
        self.assertEqual(out["permission"], "deny")
        self.assertEqual(out["user_message"], reason)
        self.assertEqual(out["agent_message"], reason)

    def test_claude_deny_and_allow(self):
        self.assert_claude(self.claude("Read", {"file_path": ".dlt/secrets.toml"}), DENY)
        self.assert_claude(self.claude("Read", {"file_path": ".dlt/config.toml"}), ALLOW)
        self.assert_claude(self.claude("Bash", {"command": "grep -r x .dlt/"}), DIRECTORY)
        self.assert_claude(self.claude("Bash", {"command": "rm -rf .claude"}), TAMPER)

    def test_cursor_file_events(self):
        self.assert_cursor(self.cursor("beforeReadFile", file_path=".dlt/secrets.toml"), DENY)
        self.assert_cursor(self.cursor("beforeReadFile", file_path=".dlt/example.secrets.toml"))
        self.assert_cursor(self.cursor("beforeTabFileRead", file_path=".env"), DENY)
        self.assert_cursor(self.cursor("beforeReadFile", file_path="notes.txt"), DENY)

    def test_cursor_shell_and_mcp_events(self):
        self.assert_cursor(self.cursor("beforeShellExecution", command="cat .env"), DENY)
        self.assert_cursor(self.cursor("beforeShellExecution", command="ls"))
        self.assert_cursor(
            self.cursor("beforeShellExecution", command="rm .claude/settings.json"), TAMPER
        )
        self.assert_cursor(
            self.cursor("beforeMCPExecution", tool_name="read_file",
                        tool_input={"path": ".dlt/secrets.toml"}), DENY
        )
        self.assert_cursor(
            self.cursor("beforeMCPExecution", tool_name="read_file",
                        tool_input={"path": "README.md"})
        )

    def test_event_name_case_decides_the_dialect(self):
        """Cursor's `preToolUse` differs from Claude's `PreToolUse` only by case.

        Lowercasing the comparison would route every Claude call into the
        Cursor dialect, whose deny JSON Claude ignores — a guard that looks
        installed and blocks nothing.
        """
        self.assert_cursor(
            self.cursor("preToolUse", tool_name="Read", tool_input={"file_path": ".env"}), DENY
        )
        self.assert_claude(self.claude("Read", {"file_path": ".env"}), DENY)

    def test_an_unrecognized_event_routes_to_claude(self):
        result = run_guard(json.dumps({
            "hook_event_name": "PostToolUse", "cwd": str(WORKSPACE),
            "tool_name": "Read", "tool_input": {"file_path": ".env"},
        }))
        self.assert_claude(result, DENY)


class FailurePolicy(unittest.TestCase):
    """Fail open on input we cannot read; fail closed once we can."""

    def assert_allow_loudly(self, result):
        """Unidentifiable input: allow, but never silently."""
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {"permission": "allow"})
        self.assertTrue(result.stderr)

    def assert_deny_loudly(self, result):
        """A guarded operation we could not clear: deny, and report why."""
        self.assertEqual(result.returncode, 0)
        reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertEqual(reason, DENY)
        self.assertTrue(result.stderr)

    def test_unparseable_stdin_allows_loudly(self):
        for payload in ("not json", '["not", "an", "object"]', "null", "5", ""):
            with self.subTest(payload=payload):
                self.assert_allow_loudly(run_guard(payload))

    def test_unjudgeable_payload_denies_loudly(self):
        self.assert_deny_loudly(run_guard(json.dumps({
            "hook_event_name": "PreToolUse", "cwd": str(WORKSPACE),
            "tool_name": "Read", "tool_input": "not a dict",
        })))
        self.assert_deny_loudly(run_guard(json.dumps({
            "hook_event_name": "PreToolUse", "cwd": str(WORKSPACE),
            "tool_name": "Bash", "tool_input": {"command": None},
        })))

    def test_cursor_dialect_also_fails_closed(self):
        result = run_guard(json.dumps({
            "hook_event_name": "beforeShellExecution", "cwd": str(WORKSPACE), "command": None,
        }))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["permission"], "deny")
        self.assertTrue(result.stderr)

    def test_an_empty_object_is_judgeable_and_allowed(self):
        result = run_guard("{}")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_missing_cwd_falls_back_to_the_process_directory(self):
        """Without `cwd` the guard resolves against its own working directory."""
        payload = json.dumps({
            "hook_event_name": "PreToolUse",
            "tool_name": "Read", "tool_input": {"file_path": ".env"},
        })
        result = run_guard(payload, cwd=str(WORKSPACE))
        self.assertEqual(result.stderr, "")
        reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertEqual(reason, DENY)


class DenyMessages(unittest.TestCase):
    """The messages are the guard's whole user interface."""

    def test_deny_names_only_always_available_tooling(self):
        # the CLI ships with dlt itself and works without the init toolkit
        self.assertIn("dlthub ai secrets view-redacted", DENY)
        self.assertIn("dlthub ai secrets update-fragment", DENY)
        # no hard dependency on a specific MCP server name or on a skill
        self.assertNotIn("dlt-workspace-mcp", DENY)
        self.assertNotIn("setup-secrets", DENY)

    def test_the_three_messages_are_distinct(self):
        self.assertEqual(len({DENY, DIRECTORY, TAMPER}), 3)


if __name__ == "__main__":
    unittest.main()
