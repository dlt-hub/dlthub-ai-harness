"""Fixtures for the job-inspector-eval deterministic checks.

`checks.py` ships inside the agent folder, which the toolkit installer copies verbatim into a
workspace. It is not a package, so the tests put its folder on the path the same way the
deployment module does.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

AGENT_DIR = (
    Path(__file__).resolve().parents[2]
    / "workbench"
    / "dlthub-platform"
    / "agents"
    / "job-inspector-eval"
)
sys.path.insert(0, str(AGENT_DIR))

import checks as C  # noqa: E402


INSPECTOR_RUN_ID = "11111111-1111-4111-8111-111111111111"
FAILED_RUN_ID = "22222222-2222-4222-8222-222222222222"
OLDER_RUN_ID = "33333333-3333-4333-8333-333333333333"


FAILED_LOG = [
    "2026-09-01 10:00:00 INFO  starting pipeline github_events",
    "2026-09-01 10:00:01 INFO  extract started",
    "2026-09-01 10:00:02 WARNING rate limited, retrying in 2s",
    "2026-09-01 10:00:05 ERROR  401 Unauthorized calling https://api.github.com/events",
    "2026-09-01 10:00:05 INFO  extract aborted",
    "Traceback (most recent call last):",
    '  File "/workspace/pipelines/github.py", line 42, in load',
    "    raise HTTPError(response)",
    "requests.exceptions.HTTPError: 401 Client Error: Unauthorized",
    "2026-09-01 10:00:06 INFO  job finished with status failed",
]


SETUP_NOISE = [
    "Building image im-Hwpd3OJtOyHlMJbGgZcsMb",
    "=> Step 1: COPY --from=ghcr.io/astral-sh/uv:latest /uv /.uv/uv",
    "  Copying blob sha256:5c3c0ad58b95a292caeabcfcb0a630993dc86ba0353fae666871bb78ef496b0e",
    "   • unpacking rootfs ...",
]
"""Real `setup` lines. Two of them match the transcript shapes, so the phase filter matters."""

PROGRAM_START = 5
"""Program output starts after the setup lines, as it does on the runner."""


def line_no(program_index: int) -> int:
    """Log line number of a `FAILED_LOG` entry, counting the setup lines before it."""
    return PROGRAM_START + program_index


def with_setup(program: List[str]) -> List["C.LogLine"]:
    """A whole run log: platform setup lines first, then the job's own output."""
    return C.numbered(SETUP_NOISE, start=1, phase="setup") + C.numbered(
        program, start=PROGRAM_START, phase="program"
    )


def inspector_log(
    events: Optional[List[str]] = None, result_json: Optional[str] = None
) -> List["C.LogLine"]:
    """A job log in the shape the launcher prints at verbosity 1, setup noise included."""
    lines = [
        "",
        "── job-inspector ──────────────────── sonnet · max 30 turns · 1,000,000 tokens ──",
        "",
        "prompt",
        "  Go ahead",
        "",
        "turn 1                                                    1,200 in / 80 out",
    ]
    lines += events if events is not None else DEFAULT_EVENTS
    lines += [
        "",
        "── succeeded ─────────────────────────── 3 turns · 12,000 tokens · $0.12 ──",
        "  tools: Bash · mcp tools: dlthub_get_run, dlthub_get_run_logs",
        "",
    ]
    if result_json is not None:
        lines += [
            "Result  [dlthub-platform:job-inspector]",
            "  status:     succeeded",
            "  summary:    the job could not authenticate",
            f"  job-run: {FAILED_RUN_ID}",
            "  loop:       claude-agent-sdk on anthropic:claude-sonnet-5, 3 turns, 12,000 tokens",
        ]
        lines += result_json.splitlines()
    return with_setup(lines)


DEFAULT_EVENTS = [
    "  thinks  I will read the run record before anything else.",
    f'  dlthub_get_run (dlthub)  {{"run_id": "{FAILED_RUN_ID}"}}',
    f'     → {{"id": "{FAILED_RUN_ID}", "status": "failed"}}',
    "  thinks  Now the log, earliest error first.",
    f'  dlthub_get_run_logs (dlthub)  {{"run_id": "{FAILED_RUN_ID}"}}',
    "     → 10 lines",
    "",
    "says",
    "  The job failed on a 401 from the GitHub API.",
]


def output(**overrides: Any) -> Dict[str, Any]:
    """A credible inspector output, with the fields a test cares about overridden."""
    base: Dict[str, Any] = {
        "status": "succeeded",
        "summary": "The `github_events` job failed: the GitHub token was rejected with 401.",
        "failed_run_id": FAILED_RUN_ID,
        "failed_job_ref": "pipelines.github_events",
        "classification": "credentials",
        "confidence": "high",
        "evidence": [
            {
                "source": f"`dlthub job runs logs {FAILED_RUN_ID}` line {line_no(3)}",
                "excerpt": "ERROR  401 Unauthorized calling https://api.github.com/events",
            }
        ],
        "proposed_fix": "Rotate the GitHub token and set it as a workspace variable.",
        "requires_human": True,
    }
    base.update(overrides)
    return base


def trace(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "loop_type": "claude-agent-sdk",
        "model": "anthropic:claude-sonnet-5",
        "inputs": {
            "failed_run_id": FAILED_RUN_ID,
            "failed_job_ref": "",
            "run_context": {"trigger": "job.fail:pipelines.github_events"},
        },
        "turn_count": 3,
        "total_tokens": 12000,
        "skills_used": ["dlthub-platform:debug-deployment"],
        "tools_used": ["Bash"],
        "mcp_tools_used": ["dlthub_get_run", "dlthub_get_run_logs"],
    }
    base.update(overrides)
    return base


def failed_run(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "id": FAILED_RUN_ID,
        "number": 12,
        "job_ref": "pipelines.github_events",
        "status": "failed",
        "trigger": "schedule:0 * * * *",
        "profile": "prod",
        "created_at": "2026-09-01T10:00:00Z",
        "pipelines": [],
    }
    base.update(overrides)
    return base


def context(**overrides: Any) -> "C.EvalContext":
    """An `EvalContext` over the fixtures, with any field replaced."""
    log = overrides.pop("inspector_log", None) or inspector_log()
    fields: Dict[str, Any] = {
        "inspector_run": {
            "id": INSPECTOR_RUN_ID,
            "job_ref": "jobs.job_inspector",
            "status": "succeeded",
            "created_at": "2026-09-01T10:05:00Z",
            "trigger": "job.fail:pipelines.github_events",
        },
        "output": output(),
        "trace": trace(),
        "inspector_log": log,
        "events": C.parse_transcript(log),
        "failed_run": failed_run(),
        "failed_log": with_setup(FAILED_LOG),
        "neighbours": [
            {"id": FAILED_RUN_ID, "number": 12, "status": "failed",
             "created_at": "2026-09-01T10:00:00Z"},
            {"id": OLDER_RUN_ID, "number": 11, "status": "succeeded",
             "created_at": "2026-09-01T09:00:00Z"},
        ],
        "pipeline_trace": None,
        "max_runs_read": C.DEFAULT_MAX_RUNS_READ,
    }
    fields.update(overrides)
    if "inspector_log" in overrides and "events" not in overrides:
        fields["events"] = C.parse_transcript(fields["inspector_log"])
    return C.EvalContext(**fields)


class StubFetcher(C.Fetcher):
    """In-memory platform, so `prepare` runs offline."""

    def __init__(
        self,
        records: Dict[str, Dict[str, Any]],
        logs: Dict[str, List["C.LogLine"]],
        results: Optional[Dict[str, Dict[str, Any]]] = None,
        runs_by_job: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        traces: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.records = records
        self.logs = logs
        self.results = results or {}
        self.runs_by_job = runs_by_job or {}
        self.traces = traces or {}

    def run_record(self, run_id: str) -> Dict[str, Any]:
        if run_id not in self.records:
            raise KeyError(run_id)
        return self.records[run_id]

    def run_log(self, run_id: str) -> List["C.LogLine"]:
        return self.logs.get(run_id, [])

    def run_result(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self.results.get(run_id)

    def job_runs(self, job_ref: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.runs_by_job.get(job_ref, [])[:limit]

    def pipeline_trace(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self.traces.get(run_id)


@pytest.fixture
def ctx() -> "C.EvalContext":
    return context()


DEPLOYED_RUN_LOG = Path(__file__).parent / "fixtures" / "deployed_inspector_run.log"
"""The `program` output of a real deployed inspector run, ids and workspace name replaced.

Run #3 of `job_inspector`, 2026-09-22. All 11 tool calls sit inside a spoken block, which is
the shape dlt-hub/dlthub-ai-workbench-internal#83 reported.
"""

DEPLOYED_RUN_TOOLS = [
    "Bash",
    "dlthub_workspace_info",
    "dlthub_list_runs",
    "dlthub_get_run",
    "dlthub_get_run_logs",
    "dlthub_get_job",
    "dlthub_telemetry_status",
    "dlthub_list_pipeline_runs",
    "dlthub_grep_run_logs",
    "dlthub_get_pipeline_run_trace",
    "Read",
]
"""The 11 calls that run made, in order. Its trace recorded 11, the evaluator read 0."""


def deployed_run_log(result_json: Optional[str] = None) -> List["C.LogLine"]:
    """The captured run as a whole job log: platform setup lines, then its own output."""
    program = DEPLOYED_RUN_LOG.read_text(encoding="utf-8").splitlines()
    if result_json is not None:
        program += [
            "Result  [dlthub-platform:job-inspector]",
            "  status:     succeeded",
            "  summary:    the pipeline could not reach the API",
        ] + result_json.splitlines()
    return with_setup(program)


def deployed_run_trace(**overrides: Any) -> Dict[str, Any]:
    """The trace that run reported: 11 uses over 5 turns, and the names behind them."""
    base = trace(
        turn_count=5,
        total_tokens=80708,
        tools_used=["Bash", "Read"],
        mcp_tools_used=[name for name in DEPLOYED_RUN_TOOLS if name.startswith("dlthub_")],
        inputs={
            "failed_run_id": "",
            "failed_job_ref": "",
            "run_context": {"trigger": "job.fail:jobs.jaffle_shop.load_jaffle_bad_config"},
        },
    )
    base.update(overrides)
    return base
