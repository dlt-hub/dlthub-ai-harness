"""A window of captured inspector runs, composed from the single-run captures.

`prepare_batch` grades every inspector run of one job in a window, and each capture under
`fixtures/captured/` holds one run. `window` merges several into one `FileFetcher` root at
test time, so the window's composition is read in the test rather than committed as a tenth
capture duplicating files the repository already holds.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import checks as C

from test_captured_runs import CAPTURED

INSPECTOR_JOB = "jobs.__deployment__.job_inspector"
CASES = ("dq_missing_input", "config_missing_destination_type", "aborted_on_data_tool")
"""A run that broke nine rules, a run that broke two, and one that reached the destination."""
SINCE = datetime(2026, 9, 20, tzinfo=timezone.utc)
UNTIL = datetime(2026, 9, 25, tzinfo=timezone.utc)
NEWEST_FIRST = ("config_missing_destination_type", "aborted_on_data_tool", "dq_missing_input")


def run_id(case: str) -> str:
    return sorted((CAPTURED / case / "results").glob("*.json"))[0].stem


def window(root: Path, *cases: str) -> C.FileFetcher:
    """The captures of `cases` under one root, with the inspector's run list rebuilt."""
    for case in cases:
        source = CAPTURED / case
        for folder in ("runs", "logs", "results", "pipeline_traces", "job_runs"):
            if not (source / folder).is_dir():
                continue
            (root / folder).mkdir(parents=True, exist_ok=True)
            for path in (source / folder).glob("*.json"):
                # the inspector's own run list is rebuilt below from the runs in the window
                if folder == "job_runs" and path.stem == INSPECTOR_JOB:
                    continue
                shutil.copy(path, root / folder / path.name)
    records = [
        json.loads((root / "runs" / f"{run_id(case)}.json").read_text(encoding="utf-8"))
        for case in cases
    ]
    records.sort(key=lambda record: str(record["created_at"]), reverse=True)
    (root / "job_runs").mkdir(parents=True, exist_ok=True)
    (root / "job_runs" / f"{INSPECTOR_JOB}.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    return C.FileFetcher(str(root))


def batch_of(root: Path, *cases: str) -> C.BatchPrep:
    return C.prepare_batch(
        {"run_id": "local", "trigger": "schedule:0 7 * * 1"},
        fetcher=window(root, *cases),
        inspector_job_ref=INSPECTOR_JOB,
        since=SINCE,
        until=UNTIL,
    )


def evaluations_of(batch: C.BatchPrep):
    """Each run finalized with the judge's checks left `N/A`, so only Python's results stand."""
    finals = []
    for prep in batch.preps:
        answers = [{"id": id, "kind": "judge", "outcome": "N/A", "reasoning": "not judged here"}
                   for id in C.judge_ids(prep.results)]
        finals.append(C.finalize({"status": "succeeded", "summary": "", "checks": answers},
                                 prep))
    return finals


def test_the_window_grades_every_captured_run_newest_first(tmp_path):
    batch = batch_of(tmp_path, *CASES)
    assert batch.aborted is False
    assert batch.skipped == []
    assert batch.found == 3
    assert [prep.inspector_run_id for prep in batch.preps] == [
        run_id(case) for case in NEWEST_FIRST
    ]
    assert batch.window["runs_evaluated"] == 3
    assert batch.capped is False


def test_every_run_in_the_window_replays_without_a_parser_fault(tmp_path):
    """The merged root serves each run what its own capture served it."""
    batch = batch_of(tmp_path, *CASES)
    for prep in batch.preps:
        assert prep.errors == []
        assert prep.problems == []
        assert prep.ctx.transcript_blind is False
        assert {call.tool for call in prep.ctx.tool_calls} == set(prep.ctx.tools_recorded)


def test_the_window_reports_its_bounds_the_counts_and_every_run(tmp_path):
    batch = batch_of(tmp_path, *CASES)
    evaluations = evaluations_of(batch)
    final = C.finalize_batch(evaluations, batch)
    assert final["window"]["runs_found"] == 3
    assert final["window"]["runs_evaluated"] == 3
    assert [entry["inspector_run_id"] for entry in final["evaluations"]] == [
        run_id(case) for case in NEWEST_FIRST
    ]
    assert final["decided_count"] == sum(entry["decided_count"] for entry in evaluations)
    summary = final["summary"]
    assert "2026-09-20T00:00:00+00:00 to 2026-09-25T00:00:00+00:00" in summary
    for case in CASES:
        assert f"`{run_id(case)}`" in summary
    assert summary.count("`") % 2 == 0


def test_a_check_broken_on_several_runs_is_counted_over_them(tmp_path):
    """Two of the three ran on `prod`, and the window says so once with the count."""
    batch = batch_of(tmp_path, *CASES)
    evaluations = evaluations_of(batch)
    counts = C.check_counts(evaluations)
    assert counts["agent_profile_not_prod"] == {"false": 2, "decided": 3}
    final = C.finalize_batch(evaluations, batch)
    assert final["passed"] is False
    assert "FALSE 2/3" in final["summary"]
    assert "Security rule broken: " in final["summary"]


def test_the_window_findings_carry_the_reasonings_of_the_runs_that_broke(tmp_path):
    batch = batch_of(tmp_path, *CASES)
    findings = json.loads(
        C.window_findings(evaluations_of(batch), batch)["window_findings"]
    )
    assert findings["job_ref"] == INSPECTOR_JOB
    assert findings["runs_evaluated"] == 3
    broken = {entry["check_id"]: entry for entry in findings["broken_checks"]}
    profile = broken["agent_profile_not_prod"]
    assert (profile["runs_broken"], profile["runs_decided"]) == (2, 3)
    assert len(profile["reasonings"]) == 2
    assert "prod" in profile["reasonings"][0]
    # a rule only the earlier definition broke is counted over the runs that decided it
    assert broken["evidence_has_provenance"]["runs_broken"] == 1


def test_a_run_with_no_stored_result_is_graded_from_its_log_envelope(tmp_path):
    """The launcher prints the result, so a window survives a run whose result is gone."""
    batch_root = tmp_path / "window"
    fetcher = window(batch_root, *CASES)
    (batch_root / "results" / f"{run_id('dq_missing_input')}.json").unlink()
    batch = C.prepare_batch(
        {"run_id": "local"}, fetcher=fetcher, inspector_job_ref=INSPECTOR_JOB,
        since=SINCE, until=UNTIL,
    )
    assert batch.skipped == []
    assert [prep.inspector_run_id for prep in batch.preps] == [
        run_id(case) for case in NEWEST_FIRST
    ]


def test_a_run_that_declared_no_result_is_skipped_with_the_reason(tmp_path):
    batch_root = tmp_path / "window"
    fetcher = window(batch_root, *CASES)
    dropped = run_id("dq_missing_input")
    (batch_root / "results" / f"{dropped}.json").unlink()
    (batch_root / "logs" / f"{dropped}.json").unlink()
    batch = C.prepare_batch(
        {"run_id": "local"}, fetcher=fetcher, inspector_job_ref=INSPECTOR_JOB,
        since=SINCE, until=UNTIL,
    )
    assert [prep.inspector_run_id for prep in batch.preps] == [
        run_id(case) for case in NEWEST_FIRST if case != "dq_missing_input"
    ]
    assert [entry["run_id"] for entry in batch.skipped] == [dropped]
    assert "no result" in batch.skipped[0]["reason"]
    assert batch.window["runs_found"] == 3
    assert batch.window["runs_skipped"] == 1


def test_a_window_holding_one_capture_is_the_single_run_evaluation(tmp_path):
    """The batch path over one run answers what `prepare` answers for that run alone."""
    batch = batch_of(tmp_path, "config_missing_destination_type")
    alone = C.prepare(
        {"run_id": "local"},
        fetcher=C.FileFetcher(str(CAPTURED / "config_missing_destination_type")),
        inspector_run_id=run_id("config_missing_destination_type"),
    )
    assert len(batch.preps) == 1
    assert {id: result.outcome for id, result in batch.preps[0].results.items()} == {
        id: result.outcome for id, result in alone.results.items()
    }
