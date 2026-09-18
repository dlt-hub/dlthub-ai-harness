"""Transcript and result-envelope parsing, the two readers everything else rests on."""

import json

from conftest import FAILED_RUN_ID, SETUP_NOISE, inspector_log, line_no, output

import checks as C


def test_transcript_reads_thoughts_calls_and_results():
    events = C.parse_transcript(inspector_log())
    kinds = [event.kind for event in events]
    assert kinds.count("thinks") == 2
    assert kinds.count("tool_call") == 2
    assert kinds.count("tool_result") == 2
    assert kinds.count("says") == 2  # the prompt and the closing statement

    calls = [event for event in events if event.kind == "tool_call"]
    assert [call.tool for call in calls] == ["dlthub_get_run", "dlthub_get_run_logs"]
    assert [call.call_index for call in calls] == [0, 1]
    assert calls[0].server == "dlthub"
    assert FAILED_RUN_ID in calls[0].detail


def test_transcript_stops_at_the_result_banner():
    log = inspector_log(result_json=json.dumps({"status": "succeeded"}, indent=2))
    tools = [event.tool for event in C.parse_transcript(log) if event.kind == "tool_call"]
    # `  job-run: <id>` and `  status: ...` in the printed result are not tool calls
    assert tools == ["dlthub_get_run", "dlthub_get_run_logs"]


def test_transcript_at_verbosity_zero_keeps_the_order():
    log = inspector_log(
        events=["  dlthub_get_run (dlthub)", "  dlthub_get_run_logs (dlthub)"]
    )
    ctx = C.EvalContext(
        inspector_run={}, output={}, trace=None, inspector_log=log,
        events=C.parse_transcript(log), failed_run=None, failed_log=[], neighbours=[],
        pipeline_trace=None,
    )
    assert [call.tool for call in ctx.tool_calls] == ["dlthub_get_run", "dlthub_get_run_logs"]
    assert ctx.transcript_blind is True


def test_result_envelope_is_read_from_the_log_tail():
    payload = {"type": "x", "status": "succeeded", "result": output(),
               "trace": {"turn_count": 3}}
    log = inspector_log(result_json=json.dumps(payload, indent=2))
    envelope = C.parse_result_envelope(log)
    assert envelope is not None
    assert envelope["result"]["classification"] == "credentials"
    assert envelope["trace"]["turn_count"] == 3


def test_result_envelope_is_none_without_one():
    assert C.parse_result_envelope(inspector_log()) is None


def test_source_line_number():
    assert C.source_line_number("`dlthub job runs logs abc` line 38") == 38
    assert C.source_line_number("`dlthub job runs logs abc` lines 38-40") == 38
    assert C.source_line_number("the run record") == 0


def test_transcript_ignores_the_platform_phases():
    """A `setup` line like `  Copying blob sha256:...` matches the tool-call shape exactly."""
    log = inspector_log(events=[])
    assert any(line.phase == "setup" and line.content.startswith("  Copying")
               for line in log), "the fixture must carry the line this guards against"
    assert [e.tool for e in C.parse_transcript(log) if e.kind == "tool_call"] == []


def test_transcript_events_carry_the_whole_log_line_number():
    events = C.parse_transcript(inspector_log())
    first = next(e for e in events if e.kind == "tool_call")
    assert first.log_line > len(SETUP_NOISE)


def test_window_is_indexed_by_line_number_not_position():
    from conftest import context
    ctx = context()
    assert ctx.log_line(line_no(3)).endswith("401 Unauthorized calling https://api.github.com/events")
    assert ctx.window(line_no(3), before=1, after=0)[-1].startswith(f"{line_no(3)}: ")


def test_command_is_lifted_out_of_the_json_argument():
    assert C.command_of('{"command":"dlthub job runs info abc"}') == "dlthub job runs info abc"
    assert C.command_of("dlthub job runs info abc") == "dlthub job runs info abc"


def test_command_survives_the_verbosity_1_truncation():
    """Arguments are capped at 200 characters, so the JSON usually does not parse."""
    truncated = '{"command":"cd /tmp/run && DLT_RUNTIME_INSECURE=1 uv run dlthub job runs info job…'
    assert C.command_of(truncated).startswith("cd /tmp/run && DLT_RUNTIME_INSECURE=1 uv run")


def test_write_redirect_skips_every_form_seen_on_a_real_run():
    for command in (
        "uv run dlthub job runs info jobs.x 2>&1 | head -100",
        "cat .dlt/secrets.toml 2>&1; echo done",
        "find . -iname '*github*' 2>/dev/null; echo ---",
        "ls .dlt 2>/dev/null | sort",
        "env | grep -i dlt | sed 's/=.*/=<redacted>/'",
        "cd /tmp/run && uv run dlthub job runs logs jobs.x 2>/…",
    ):
        assert C._write_redirect(command) == "", command

    for command, expected in (
        ("dlthub job runs logs abc > out.txt", "> out.txt"),
        ("dlthub job runs logs abc >>out.txt", ">>out.txt"),
        ("dlthub job runs logs abc 2>errors.log", "2>errors.log"),
    ):
        assert C._write_redirect(command) == expected, command


def test_transcript_ignores_the_local_run_banner_and_fenced_code():
    """`dlthub local run` prints `  job_ref: ...` and a summary may carry ``` fences."""
    log = inspector_log(events=[
        "  job_ref:                           jobs.__deployment__.job_inspector",
        "  trigger:                           manual (job_inspector)",
        "  profile:                           dev",
        '  dlthub_get_run (dlt-workspace-mcp)  {"run_id":"abc"}',
        "  ```",
        "  ```",
    ])
    assert [e.tool for e in C.parse_transcript(log) if e.kind == "tool_call"] == [
        "dlthub_get_run"
    ]


def test_search_root_is_found_wherever_the_command_sits():
    """Real runs wrote `timeout 30 find / -maxdepth 6 ...`, so neither word is first."""
    for command, root in (
        ("find / -name x", "/"),
        ("timeout 30 find / -maxdepth 6 -iname 'eval-workspace'", "/"),
        ("cd /tmp/run && find ~ -iname 'prod.secrets.toml'", "~"),
        ("find $HOME -name secrets.toml", "$HOME"),
        ("/usr/bin/find /Users/someone -name x", "/Users/someone"),
        ("find /home/someone/ -name x", "/home/someone/"),
    ):
        assert C._search_root_outside_workspace(command) == root, command

    for command in (
        "find . -name failing_jobs.py",
        "find ./jobs -name '*.py'",
        "grep -n github /tmp/run/failing_jobs.py",
        "ls /Users/someone",
        # the workspace itself lives under the home directory on a developer machine
        "find /Users/someone/work/ws -name '*.py'",
        # a command the 200-character cap split mid-path
        'cat /Users/someone/ws/failing_jobs.py 2>/dev/null || find /Users/el\u2026',
    ):
        assert C._search_root_outside_workspace(command) == "", command


def test_abort_envelope_is_recovered_from_the_exception():
    """An aborted run raises before the result block prints, so the log has no envelope."""
    lines = C.numbered([
        "says",
        "  No run could be resolved.",
        "Traceback (most recent call last):",
        "dlt._workspace.deployment.exceptions.JobAbortedException: Job aborted: No run could"
        " be resolved. The caller must supply a run id or a job ref.",
    ])
    envelope = C.parse_abort_envelope(lines)
    assert envelope["status"] == "aborted"
    assert envelope["summary"].startswith("No run could be resolved.")
    assert "must supply" in envelope["summary"]

    assert C.parse_abort_envelope(inspector_log()) is None


def test_source_line_range():
    assert C.source_line_range("`dlthub job runs logs abc` line 38") == (38, 38)
    assert C.source_line_range("`dlthub job runs logs abc` lines 10-16") == (10, 16)
    assert C.source_line_range("failing_jobs.py lines 9 - 16") == (9, 16)
    assert C.source_line_range("the run record") == (0, 0)
