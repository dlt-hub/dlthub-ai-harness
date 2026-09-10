"""End-to-end tests for workbench/init/hooks/secrets_guard.py.

Runs the guard as a subprocess exactly the way the agents do: payload on
stdin, decision read from stdout JSON + exit code. Path checks run against a
real temp workspace so glob expansion has something to expand onto.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "workbench" / "init" / "hooks" / "secrets_guard.py"


def run_guard(stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )


class GuardTestCase(unittest.TestCase):
    """A temp dlt workspace, plus assertions in each agent's dialect."""

    @classmethod
    def setUpClass(cls):
        cls.workspace = Path(tempfile.mkdtemp(prefix="dlt-guard-test-"))
        (cls.workspace / ".dlt").mkdir()
        (cls.workspace / ".dlt" / "secrets.toml").write_text("password='REAL'\n")
        (cls.workspace / ".dlt" / "dev.secrets.toml").write_text("password='REAL'\n")
        (cls.workspace / ".dlt" / "example.secrets.toml").write_text("password='<set me>'\n")
        (cls.workspace / ".dlt" / "config.toml").write_text("[runtime]\n")
        (cls.workspace / ".env").write_text("API_KEY=REAL\n")
        (cls.workspace / ".env.example").write_text("API_KEY=\n")
        (cls.workspace / "pyproject.toml").write_text("[project]\n")
        (cls.workspace / "src").mkdir()
        (cls.workspace / "src" / "pipeline.py").write_text("import dlt\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workspace, ignore_errors=True)

    # payload builders

    def claude(self, tool_name, tool_input) -> subprocess.CompletedProcess:
        return run_guard(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "cwd": str(self.workspace),
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                }
            )
        )

    def bash(self, command) -> subprocess.CompletedProcess:
        return self.claude("Bash", {"command": command})

    def cursor(self, event, **fields) -> subprocess.CompletedProcess:
        return run_guard(
            json.dumps({"hook_event_name": event, "cwd": str(self.workspace), **fields})
        )

    # assertions

    def assert_claude_deny(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertTrue(decision["permissionDecisionReason"])

    def assert_claude_allow(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def assert_cursor_deny(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["permission"], "deny")
        self.assertTrue(out["user_message"])
        self.assertTrue(out["agent_message"])

    def assert_cursor_allow(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"permission": "allow"})


class FileNameTest(GuardTestCase):
    def test_read_secrets_toml_denied(self):
        self.assert_claude_deny(self.claude("Read", {"file_path": ".dlt/secrets.toml"}))

    def test_read_profile_secrets_toml_denied(self):
        self.assert_claude_deny(self.claude("Read", {"file_path": ".dlt/dev.secrets.toml"}))

    def test_read_example_secrets_toml_allowed(self):
        self.assert_claude_allow(self.claude("Read", {"file_path": ".dlt/example.secrets.toml"}))

    def test_read_template_secrets_toml_allowed(self):
        self.assert_claude_allow(self.claude("Read", {"file_path": ".dlt/template.secrets.toml"}))

    def test_read_uppercase_secrets_toml_denied(self):
        self.assert_claude_deny(self.claude("Read", {"file_path": ".dlt/SECRETS.TOML"}))

    def test_read_uppercase_env_denied(self):
        self.assert_claude_deny(self.claude("Read", {"file_path": ".ENV"}))

    def test_read_env_example_allowed(self):
        self.assert_claude_allow(self.claude("Read", {"file_path": ".env.example"}))

    def test_read_dlt_config_allowed(self):
        self.assert_claude_allow(self.claude("Read", {"file_path": ".dlt/config.toml"}))

    def test_backup_copy_denied(self):
        self.assert_claude_deny(self.claude("Read", {"file_path": ".dlt/secrets.toml.bak"}))

    def test_editor_swapfile_denied(self):
        self.assert_claude_deny(self.claude("Read", {"file_path": ".env~"}))

    def test_backup_of_placeholder_allowed(self):
        self.assert_claude_allow(self.claude("Read", {"file_path": ".env.example.bak"}))

    def test_envrc_denied(self):
        self.assert_claude_deny(self.claude("Read", {"file_path": ".envrc"}))

    def test_credential_files_denied(self):
        for path in (
            "~/.netrc",
            "~/.pgpass",
            "service_account.json",
            "~/.aws/credentials",
            "~/.ssh/id_ed25519",
        ):
            with self.subTest(path=path):
                self.assert_claude_deny(self.claude("Read", {"file_path": path}))

    def test_public_key_allowed(self):
        self.assert_claude_allow(self.claude("Read", {"file_path": "~/.ssh/id_ed25519.pub"}))


class GrepTest(GuardTestCase):
    def test_paths_as_string_denied(self):
        self.assert_claude_deny(self.claude("Grep", {"paths": ".dlt/secrets.toml"}))

    def test_paths_as_list_denied(self):
        self.assert_claude_deny(self.claude("Grep", {"paths": ["src/", ".env.production"]}))

    def test_glob_denied(self):
        self.assert_claude_deny(self.claude("Grep", {"glob": "secrets.toml"}))

    def test_harmless_allowed(self):
        self.assert_claude_allow(self.claude("Grep", {"paths": ["src/"], "path": "README.md"}))

    def test_pattern_naming_a_secrets_file_allowed(self):
        # searching *for the string* "secrets.toml" reveals nothing
        self.assert_claude_allow(self.claude("Grep", {"pattern": "secrets.toml", "path": "src"}))


class ShellTest(GuardTestCase):
    def test_plain_cat_denied(self):
        self.assert_claude_deny(self.bash("cat .dlt/secrets.toml"))

    def test_redirect_without_space_denied(self):
        # shlex.split alone returns ['cat<.env'] and matches nothing
        self.assert_claude_deny(self.bash("cat<.env"))

    def test_pipe_without_space_denied(self):
        self.assert_claude_deny(self.bash("cat .env|head"))

    def test_glob_over_secrets_dir_denied(self):
        self.assert_claude_deny(self.bash("cat .dlt/*"))
        self.assert_claude_deny(self.bash("cat .dlt/*.toml"))

    def test_dotenv_glob_denied(self):
        self.assert_claude_deny(self.bash("cat .env*"))

    def test_bulk_reader_on_secrets_dir_denied(self):
        self.assert_claude_deny(self.bash("grep -r password .dlt/"))
        self.assert_claude_deny(self.bash("tar cf - .dlt | base64"))

    def test_interpreter_inline_code_denied(self):
        self.assert_claude_deny(self.bash("bash -c 'cat .env'"))
        self.assert_claude_deny(self.bash("python3 -c \"print(open('.env').read())\""))

    def test_environment_dump_denied(self):
        self.assert_claude_deny(self.bash("env"))
        self.assert_claude_deny(self.bash("printenv | grep -i key"))

    def test_env_as_command_prefix_allowed(self):
        self.assert_claude_allow(self.bash("env FOO=1 python src/pipeline.py"))

    def test_listing_secrets_dir_allowed(self):
        # names only, no contents
        self.assert_claude_allow(self.bash("ls -la .dlt"))

    def test_unrelated_globs_allowed(self):
        self.assert_claude_allow(self.bash("cat *.toml"))
        self.assert_claude_allow(self.bash("cat src/*.py"))

    def test_prose_mentioning_dotenv_allowed(self):
        self.assert_claude_allow(self.bash("git commit -m 'fix .env loading'"))

    def test_cat_readme_allowed(self):
        self.assert_claude_allow(self.bash("cat README.md"))


class OtherToolsTest(GuardTestCase):
    """Reachable only with matcher "*" — see hooks/hooks.json."""

    def test_write_to_dotenv_denied(self):
        self.assert_claude_deny(self.claude("Write", {"file_path": ".env", "content": "x"}))

    def test_edit_secrets_denied(self):
        self.assert_claude_deny(
            self.claude("Edit", {"file_path": ".dlt/secrets.toml", "old_string": "a", "new_string": "b"})
        )

    def test_codex_apply_patch_denied(self):
        self.assert_claude_deny(self.claude("apply_patch", {"file_path": ".env"}))

    def test_mcp_tool_reading_secrets_denied(self):
        self.assert_claude_deny(
            self.claude("mcp__filesystem__read_file", {"path": ".dlt/secrets.toml"})
        )

    def test_mcp_tool_with_unrelated_prose_allowed(self):
        self.assert_claude_allow(
            self.claude("mcp__linear__list_issues", {"query": "check .env handling"})
        )

    def test_write_to_source_file_allowed(self):
        self.assert_claude_allow(self.claude("Write", {"file_path": "src/pipeline.py", "content": "x"}))


class TamperTest(GuardTestCase):
    def test_deleting_the_guard_denied(self):
        self.assert_claude_deny(self.bash("rm .agents/hooks/secrets_guard.py"))

    def test_rewriting_hook_config_denied(self):
        self.assert_claude_deny(self.bash("sed -i '' 's/secrets_guard//' .claude/settings.json"))

    def test_editing_the_guard_denied(self):
        result = self.claude(
            "Edit",
            {"file_path": ".agents/hooks/secrets_guard.py", "old_string": "a", "new_string": "b"},
        )
        self.assert_claude_deny(result)

    def test_reading_hook_config_allowed(self):
        # reading the config is fine; only rewriting it is refused
        self.assert_claude_allow(self.bash("cat .claude/settings.json"))


class CursorDialectTest(GuardTestCase):
    def test_read_file_denied(self):
        self.assert_cursor_deny(self.cursor("beforeReadFile", file_path=".dlt/secrets.toml"))

    def test_read_file_allowed(self):
        self.assert_cursor_allow(self.cursor("beforeReadFile", file_path=".dlt/example.secrets.toml"))

    def test_tab_file_read_denied(self):
        self.assert_cursor_deny(self.cursor("beforeTabFileRead", file_path=".env"))

    def test_shell_denied(self):
        self.assert_cursor_deny(self.cursor("beforeShellExecution", command="cat .env"))

    def test_shell_allowed(self):
        self.assert_cursor_allow(self.cursor("beforeShellExecution", command="ls"))

    def test_mcp_execution_denied(self):
        self.assert_cursor_deny(
            self.cursor(
                "beforeMCPExecution",
                tool_name="read_file",
                tool_input={"path": ".dlt/secrets.toml"},
            )
        )

    def test_pre_tool_use_denied(self):
        # Cursor's "preToolUse" differs from Claude's "PreToolUse" only by case
        self.assert_cursor_deny(
            self.cursor("preToolUse", tool_name="Read", tool_input={"file_path": ".env"})
        )

    def test_claude_pre_tool_use_keeps_claude_dialect(self):
        self.assert_claude_deny(self.claude("Read", {"file_path": ".env"}))


class FailurePolicyTest(GuardTestCase):
    def test_read_with_string_tool_input_denied(self):
        result = self.claude("Read", "not a dict")
        self.assert_claude_deny(result)
        self.assertTrue(result.stderr)

    def test_cursor_shell_null_command_denied(self):
        result = self.cursor("beforeShellExecution", command=None)
        self.assert_cursor_deny(result)
        self.assertTrue(result.stderr)

    def assert_allow_loud(self, result):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {"permission": "allow"})
        self.assertTrue(result.stderr)

    def test_garbage_stdin_allows_loudly(self):
        self.assert_allow_loud(run_guard("not json"))

    def test_list_payload_allows_loudly(self):
        self.assert_allow_loud(run_guard('["not", "an", "object"]'))


class DenyMessageTest(GuardTestCase):
    def test_names_only_always_available_tooling(self):
        result = self.claude("Read", {"file_path": ".env"})
        reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        # the CLI ships with dlt itself and works without the init toolkit
        self.assertIn("dlthub ai secrets view-redacted", reason)
        self.assertIn("dlthub ai secrets update-fragment", reason)
        # no hard dependency on a specific MCP server name or on a skill
        self.assertNotIn("dlt-workspace-mcp", reason)
        self.assertNotIn("setup-secrets", reason)


if __name__ == "__main__":
    unittest.main()
