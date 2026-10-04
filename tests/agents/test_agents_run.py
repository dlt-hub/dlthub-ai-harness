"""The toolkit's agents run as a user declares them: `run.agent("<toolkit>:<agent>")`.

Each test checks the returned output and `last_job_result`. The model is `TestModel`.
"""

import ast
import glob
import json
import os
from pathlib import Path

import pytest

from dlt.hub import run

REPO = Path(__file__).resolve().parents[2]
NULL_LOOP = "null-pydantic-ai"
FAILED_RUN_ID = "3f2b9c1e-8a4d-4e6f-9b2a-1c3d5e7f9a0b"
CAPTURED = REPO / "tests" / "job_inspector_eval" / "fixtures" / "captured"
JUDGE_ANSWERS = REPO / "tests" / "job_inspector_eval" / "fixtures" / "judge_answers"
AGENTS = REPO / "workbench" / "dlthub-platform" / "agents"


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


def _capture(name: str) -> tuple:
    directory = CAPTURED / name
    run_id = os.path.basename(glob.glob(str(directory / "results" / "*.json"))[0])[:-5]
    return str(directory), run_id


@pytest.mark.asyncio
async def test_job_inspector_eval_grades_a_captured_run(workspace: Path, null_loop: type) -> None:
    replay_dir, inspector_run_id = _capture("config_missing_destination_type")
    null_loop.output = json.loads(
        (JUDGE_ANSWERS / "config_missing_destination_type.json").read_text(encoding="utf-8")
    )
    evaluator = run.agent("dlthub-platform:job-inspector-eval")
    run_context = {
        "run_id": "r-eval",
        "trigger": "manual:",
        "refresh": False,
        "run_args": {"replay_dir": replay_dir},
    }

    evaluation = await evaluator(inspector_run_id=inspector_run_id, run_context=run_context)

    # `validate_input` prepared the evidence for the system prompt, and `validate_output`
    # finalized the result
    assert evaluation["inspector_run_id"] == inspector_run_id
    assert "passed" in evaluation and "pass_rate" in evaluation and "metrics" in evaluation
    assert evaluation["summary"].startswith("## Findings")
    kinds = {check["kind"] for check in evaluation["checks"]}
    assert {"deterministic", "judge"} <= kinds
    job_result = evaluator.last_job_result
    assert job_result["type"] == "background_agent.dlthub-platform:job-inspector-eval"
    assert {"type": "job-runs", "id": f"job-runs/{inspector_run_id}"} in job_result["object"]
    trace = job_result["trace"]
    assert trace["loop_type"] == NULL_LOOP
    assert trace["unresolved_placeholders"] == []
    assert trace["inputs"]["inspector_output"]


@pytest.mark.asyncio
async def test_job_inspector_eval_aborts_without_calling_the_model(
    workspace: Path, null_loop: type
) -> None:
    replay_dir, _ = _capture("config_missing_destination_type")
    evaluator = run.agent("dlthub-platform:job-inspector-eval")
    run_context = {
        "run_id": "r-eval",
        "trigger": "manual:",
        "refresh": False,
        "run_args": {"replay_dir": replay_dir},
    }

    # no run id, no job ref and a manual trigger: there is no inspector run to evaluate
    with pytest.raises(run.JobAbortedException, match="no inspector run could be resolved"):
        await evaluator(run_context=run_context)

    assert null_loop.models == []
    assert evaluator.last_job_result["status"] == "aborted"
