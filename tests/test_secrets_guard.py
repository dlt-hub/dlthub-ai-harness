"""End-to-end tests for workbench/init/hooks/secrets_guard.py.

Runs the guard as a subprocess exactly the way the agents do: payload on
stdin, decision read from stdout JSON + exit code.
"""

import json
import subprocess
import sys
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


def claude_payload(tool_name, tool_input) -> str:
    return json.dumps({"tool_name": tool_name, "tool_input": tool_input})


class SecretsGuardTest(unittest.TestCase):
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

    def assert_cursor_allow(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"permission": "allow"})

    # claude / codex dialect

    def test_read_secrets_toml_denied(self):
        result = run_guard(claude_payload("Read", {"file_path": ".dlt/secrets.toml"}))
        self.assert_claude_deny(result)

    def test_read_example_secrets_toml_allowed(self):
        result = run_guard(claude_payload("Read", {"file_path": ".dlt/example.secrets.toml"}))
        self.assert_claude_allow(result)

    def test_read_uppercase_secrets_toml_denied(self):
        result = run_guard(claude_payload("Read", {"file_path": ".dlt/SECRETS.TOML"}))
        self.assert_claude_deny(result)

    def test_read_uppercase_env_denied(self):
        result = run_guard(claude_payload("Read", {"file_path": ".ENV"}))
        self.assert_claude_deny(result)

    def test_read_env_example_allowed(self):
        result = run_guard(claude_payload("Read", {"file_path": ".env.example"}))
        self.assert_claude_allow(result)

    def test_grep_paths_as_string_denied(self):
        result = run_guard(claude_payload("Grep", {"paths": ".dlt/secrets.toml"}))
        self.assert_claude_deny(result)

    def test_grep_paths_as_list_denied(self):
        result = run_guard(claude_payload("Grep", {"paths": ["src/", ".env.production"]}))
        self.assert_claude_deny(result)

    def test_grep_glob_denied(self):
        result = run_guard(claude_payload("Grep", {"glob": "**/.env"}))
        self.assert_claude_deny(result)

    def test_grep_harmless_allowed(self):
        result = run_guard(claude_payload("Grep", {"paths": ["src/"], "path": "README.md"}))
        self.assert_claude_allow(result)

    def test_bash_cat_secrets_denied(self):
        result = run_guard(claude_payload("Bash", {"command": "cat secrets.toml"}))
        self.assert_claude_deny(result)

    def test_bash_cat_readme_allowed(self):
        result = run_guard(claude_payload("Bash", {"command": "cat README.md"}))
        self.assert_claude_allow(result)

    def test_unknown_tool_allowed(self):
        result = run_guard(claude_payload("Write", {"file_path": ".env"}))
        self.assert_claude_allow(result)

    # cursor dialect

    def test_cursor_read_env_denied(self):
        payload = json.dumps({"hook_event_name": "beforeReadFile", "file_path": ".env"})
        self.assert_cursor_deny(run_guard(payload))

    def test_cursor_shell_ls_allowed(self):
        payload = json.dumps({"hook_event_name": "beforeShellExecution", "command": "ls"})
        self.assert_cursor_allow(run_guard(payload))

    # fail closed: identified operation, unverifiable input

    def test_read_with_string_tool_input_denied(self):
        result = run_guard(claude_payload("Read", "not a dict"))
        self.assert_claude_deny(result)
        self.assertTrue(result.stderr)

    def test_cursor_shell_null_command_denied(self):
        payload = json.dumps({"hook_event_name": "beforeShellExecution", "command": None})
        result = run_guard(payload)
        self.assert_cursor_deny(result)
        self.assertTrue(result.stderr)

    # fail open loudly: unidentifiable input

    def assert_allow_loud(self, result):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {"permission": "allow"})
        self.assertTrue(result.stderr)

    def test_garbage_stdin_allows_loudly(self):
        self.assert_allow_loud(run_guard("not json"))

    def test_list_payload_allows_loudly(self):
        self.assert_allow_loud(run_guard('["not", "an", "object"]'))


if __name__ == "__main__":
    unittest.main()
