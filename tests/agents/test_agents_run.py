"""The toolkit's agent runs as a user declares it: `run.agent("<toolkit>:<agent>")`.

Each test checks the returned output and `last_job_result`. The model is `TestModel`.
"""

from pathlib import Path

import pytest

from dlt.hub import run

NULL_LOOP = "null-pydantic-ai"
FAILED_RUN_ID = "3f2b9c1e-8a4d-4e6f-9b2a-1c3d5e7f9a0b"


def inspector_report(summary: str) -> dict:
    return {
        "status": "succeeded",
        "summary": summary,
        "failed_run_id": FAILED_RUN_ID,
        "classification": "config",
        "confidence": "high",
        "evidence": [
            {"source": "run log", "excerpt": "destination type missing", "provenance": "run_log"}
        ],
        "open_points": [],
        "requires_human": False,
    }


@pytest.mark.asyncio
async def test_job_inspector_runs_and_links_its_summary(
    workspace: Path, null_loop: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a workspace id is all the summary links need; no token, so nothing is looked up
    monkeypatch.setenv("RUNTIME__WORKSPACE_ID", "ws-test")
    null_loop.output = inspector_report(f"- Run {FAILED_RUN_ID} of `jobs.ingest.load` failed.")
    inspector = run.agent("dlthub-platform:job-inspector")

    report = await inspector(failed_run_id=FAILED_RUN_ID)

    # the output went through `validate_output` in the agent's `agent.py`: ids became links
    assert f"/w/ws-test/runs/{FAILED_RUN_ID})" in report["summary"]
    assert "/w/ws-test/jobs/jobs.ingest.load)" in report["summary"]
    job_result = inspector.last_job_result
    assert job_result["type"] == "background_agent.dlthub-platform:job-inspector"
    assert job_result["status"] == "succeeded"
    assert job_result["result"] == report
    assert {"type": "job-runs", "id": f"job-runs/{FAILED_RUN_ID}"} in job_result["object"]
    trace = job_result["trace"]
    assert trace["loop_type"] == NULL_LOOP
    assert trace["inputs"]["failed_run_id"] == FAILED_RUN_ID
    assert trace["unresolved_placeholders"] == []
    assert trace["inlined_skills"] == ["dlthub-platform:debug-deployment"]


@pytest.mark.asyncio
async def test_job_inspector_output_generated_from_its_schema_validates(workspace: Path) -> None:
    """`TestModel` fills the output from the declared schema; dlt validates it in full."""
    inspector = run.agent("dlthub-platform:job-inspector")

    report = await inspector(failed_run_id=FAILED_RUN_ID)

    for field in ("status", "summary", "classification", "confidence", "evidence"):
        assert field in report
    assert inspector.last_job_result["status"] == report["status"]
