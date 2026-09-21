"""Resolution, fetching, the judge inputs, and writing the computed results back."""

import json

from conftest import (
    FAILED_LOG,
    SETUP_NOISE,
    line_no,
    with_setup,
    FAILED_RUN_ID,
    INSPECTOR_RUN_ID,
    OLDER_RUN_ID,
    StubFetcher,
    context,
    failed_run,
    inspector_log,
    output,
    trace,
)

import checks as C

EVALUATOR_RUN_ID = "55555555-5555-4555-8555-555555555555"

INSPECTOR_RECORD = {
    "id": INSPECTOR_RUN_ID,
    "job_ref": "jobs.job_inspector",
    "status": "succeeded",
    "created_at": "2026-09-01T10:05:00Z",
    "trigger": "job.fail:pipelines.github_events",
    "pipelines": [],
}
EVALUATOR_RECORD = {
    "id": EVALUATOR_RUN_ID,
    "job_ref": "jobs.job_inspector_eval",
    "status": "running",
    "prev_run_id": INSPECTOR_RUN_ID,
    "created_at": "2026-09-01T10:06:00Z",
}


def envelope_log() -> list:
    payload = {"type": "dlthub-platform:job-inspector", "status": "succeeded",
               "result": output(), "trace": trace()}
    return inspector_log(result_json=json.dumps(payload, indent=2))


def fetcher(**overrides) -> StubFetcher:
    records = {
        INSPECTOR_RUN_ID: INSPECTOR_RECORD,
        EVALUATOR_RUN_ID: EVALUATOR_RECORD,
        FAILED_RUN_ID: failed_run(),
    }
    logs = {INSPECTOR_RUN_ID: envelope_log(), FAILED_RUN_ID: with_setup(FAILED_LOG)}
    runs_by_job = {
        "pipelines.github_events": [
            failed_run(),
            {"id": OLDER_RUN_ID, "number": 11, "status": "succeeded",
             "created_at": "2026-09-01T09:00:00Z"},
        ],
        "jobs.job_inspector": [INSPECTOR_RECORD],
    }
    kwargs = {"records": records, "logs": logs, "runs_by_job": runs_by_job}
    kwargs.update(overrides)
    return StubFetcher(**kwargs)


# resolution


def test_given_run_id_wins():
    resolved, reason = C.resolve_inspector_run(
        {"run_id": EVALUATOR_RUN_ID}, fetcher(), inspector_run_id="explicit"
    )
    assert (resolved, reason) == ("explicit", "")


def test_prev_run_id_of_the_own_run_is_next():
    resolved, reason = C.resolve_inspector_run({"run_id": EVALUATOR_RUN_ID}, fetcher())
    assert (resolved, reason) == (INSPECTOR_RUN_ID, "")


def test_job_ref_resolves_to_the_latest_run():
    resolved, _ = C.resolve_inspector_run(
        {"run_id": "local"}, fetcher(), inspector_job_ref="jobs.job_inspector"
    )
    assert resolved == INSPECTOR_RUN_ID


def test_trigger_names_the_job_when_nothing_else_does():
    resolved, _ = C.resolve_inspector_run(
        {"run_id": "local", "trigger": "job.success:jobs.job_inspector"}, fetcher()
    )
    assert resolved == INSPECTOR_RUN_ID


def test_nothing_resolves_to_a_reason():
    resolved, reason = C.resolve_inspector_run({"run_id": "local", "trigger": "manual:"},
                                               fetcher())
    assert resolved == ""
    assert "no inspector run could be resolved" in reason


# fetching


def test_context_is_built_from_the_log_envelope_when_no_result_is_stored():
    ctx = C.build_context(INSPECTOR_RUN_ID, fetcher())
    assert ctx.output["classification"] == "credentials"
    assert ctx.trace["turn_count"] == 3
    assert ctx.failed_run["job_ref"] == "pipelines.github_events"
    assert len(ctx.failed_log) == len(FAILED_LOG) + len(SETUP_NOISE)
    assert [call.tool for call in ctx.tool_calls] == ["dlthub_get_run", "dlthub_get_run_logs"]


def test_stored_result_is_preferred_over_the_envelope():
    stored = {INSPECTOR_RUN_ID: {"result": output(classification="code"),
                                 "trace": trace(turn_count=9)}}
    ctx = C.build_context(INSPECTOR_RUN_ID, fetcher(results=stored))
    assert ctx.output["classification"] == "code"
    assert ctx.trace["turn_count"] == 9


# prepare


def test_prepare_runs_every_deterministic_check_and_builds_the_judge_inputs():
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID, "trigger": "job.success:jobs.job_inspector"},
                     fetcher=fetcher())
    assert prep.aborted is False
    assert prep.errors == []
    assert prep.inspector_run_id == INSPECTOR_RUN_ID

    deterministic = [entry.id for entry in C.CHECKS.values() if entry.fn is not None]
    assert set(prep.results) == set(deterministic)

    windows = json.loads(prep.judge_inputs["evidence_windows"])
    assert windows["open_checks"] == C.judge_ids(prep.results)
    assert windows["evidence"][0]["line"] == line_no(3)
    assert windows["earliest_error"]["cited_line"] == line_no(3)
    assert [frame["owner"] for frame in windows["traceback_frames"]] == ["workspace"]
    assert json.loads(prep.judge_inputs["inspector_output"])["classification"] == "credentials"
    assert json.loads(prep.judge_inputs["neighbour_runs"])[0]["id"] == FAILED_RUN_ID


def test_prepare_aborts_without_an_inspector_run():
    prep = C.prepare({"run_id": "local", "trigger": "manual:"}, fetcher=fetcher())
    assert prep.aborted is True
    assert prep.aborted_output["status"] == "aborted"
    assert prep.aborted_output["checks"] == []


def test_prepare_aborts_when_the_run_declared_no_result():
    logs = {INSPECTOR_RUN_ID: inspector_log(), FAILED_RUN_ID: with_setup(FAILED_LOG)}
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID}, fetcher=fetcher(logs=logs))
    assert prep.aborted is True
    assert "declared no result" in prep.abort_reason


def test_prepare_does_not_hand_the_judge_a_whole_log():
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID}, fetcher=fetcher())
    windows = json.loads(prep.judge_inputs["evidence_windows"])
    assert len(windows["log_tail"]) <= 60


# finalize


def _prep_with(**overrides) -> C.EvalPrep:
    ctx = context(**overrides)
    results, errors = C.run_deterministic(ctx)
    return C.EvalPrep(ctx=ctx, results=results, errors=errors,
                      inspector_run_id=INSPECTOR_RUN_ID)


def test_finalize_reports_one_entry_per_registered_check():
    prep = _prep_with()
    final = C.finalize({"status": "succeeded", "summary": "read them all", "checks": []}, prep)
    assert [entry["id"] for entry in final["checks"]] == list(C.CHECKS)
    assert final["inspector_run_id"] == INSPECTOR_RUN_ID
    assert final["failed_run_id"] == FAILED_RUN_ID
    assert final["inspector_status"] == "succeeded"
    assert final["metrics"]["turn_count"] == 3


def test_finalize_overwrites_a_deterministic_outcome_the_judge_rewrote():
    prep = _prep_with(output=output(evidence=[]))
    judge = {
        "status": "succeeded",
        "summary": "",
        "checks": [{"id": "succeeded_has_evidence", "kind": "judge", "outcome": "TRUE",
                    "reasoning": "looks fine to me"}],
    }
    final = C.finalize(judge, prep)
    entry = next(e for e in final["checks"] if e["id"] == "succeeded_has_evidence")
    assert entry["outcome"] == "FALSE"
    assert entry["kind"] == "deterministic"
    assert final["passed"] is False


def test_finalize_drops_an_invented_check_id():
    prep = _prep_with()
    judge = {"status": "succeeded", "summary": "",
             "checks": [{"id": "the_inspector_was_nice", "kind": "judge", "outcome": "TRUE",
                         "reasoning": "it was"}]}
    final = C.finalize(judge, prep)
    assert "the_inspector_was_nice" not in [entry["id"] for entry in final["checks"]]


def test_finalize_reports_an_unanswered_judge_check_as_not_applicable():
    prep = _prep_with()
    final = C.finalize({"status": "succeeded", "summary": "done", "checks": []}, prep)
    entry = next(e for e in final["checks"] if e["id"] == "classification_correct")
    assert entry["outcome"] == "N/A"
    assert "went unanswered" in final["summary"]


def test_an_open_check_left_unanswered_fails_the_evaluation():
    """An empty or truncated judge response would otherwise read as a clean inspector run."""
    prep = _prep_with()
    answers = [{"id": id, "kind": "judge", "outcome": "TRUE", "reasoning": "fine"}
               for id in C.judge_ids(prep.results)]

    truncated = C.finalize(
        {"status": "succeeded", "summary": "done", "checks": answers[:-1]}, prep
    )
    assert truncated["status"] == "failed"
    assert truncated["passed"] is False
    assert answers[-1]["id"] in truncated["summary"]

    empty = C.finalize({"status": "succeeded", "summary": "done", "checks": []}, prep)
    assert empty["status"] == "failed"
    assert empty["passed"] is False


def test_pass_rate_counts_only_decided_checks():
    prep = _prep_with()
    judge = {
        "status": "succeeded",
        "summary": "",
        "checks": [{"id": id, "kind": "judge", "outcome": "TRUE", "reasoning": "fine"}
                   for id in C.judge_ids(prep.results)],
    }
    final = C.finalize(judge, prep)
    decided = [e for e in final["checks"] if e["outcome"] in ("TRUE", "FALSE")]
    true_count = sum(1 for e in decided if e["outcome"] == "TRUE")
    assert final["pass_rate"] == true_count / len(decided)
    assert final["passed"] is (final["pass_rate"] == 1.0)


def test_a_check_that_raised_turns_the_run_failed():
    prep = _prep_with()
    prep.errors.append("evidence_excerpts_exist: KeyError: 'excerpt'")
    final = C.finalize({"status": "succeeded", "summary": "done", "checks": []}, prep)
    assert final["status"] == "failed"
    assert final["passed"] is False
    assert "Checks that raised" in final["summary"]


def test_finalize_fills_the_deterministic_checks_the_judge_did_not_return():
    """The judge answers only `open_checks`; the rest are merged from what Python computed."""
    prep = _prep_with()
    judge = {"status": "succeeded", "summary": "done",
             "checks": [{"id": id, "kind": "judge", "outcome": "TRUE", "reasoning": "fine"}
                        for id in C.judge_ids(prep.results)]}
    final = C.finalize(judge, prep)
    assert [entry["id"] for entry in final["checks"]] == list(C.CHECKS)
    computed = next(e for e in final["checks"] if e["id"] == "succeeded_has_evidence")
    assert computed["kind"] == "deterministic"
    assert computed["reasoning"] == prep.results["succeeded_has_evidence"].reasoning
    assert "went unanswered" not in final["summary"]


def test_earliest_error_window_says_when_it_could_not_locate_the_cited_line():
    """Seen on a real run: the judge read an empty candidate list as `no earlier error`."""
    unanchored = output(evidence=[{"source": "dlthub job runs logs abc",
                                   "excerpt": "a phrase that appears nowhere in the log"}])
    window = C.earliest_error_window(context(output=unanchored))
    assert window["located"] is False
    assert window["candidates"] == []
    assert "no anchor" in window["reason"]

    anchored = C.earliest_error_window(context())
    assert anchored["located"] is True
    assert anchored["cited_line"] == line_no(3)
    assert anchored["anchor_line"] == line_no(3)


def test_earliest_error_window_anchors_on_the_line_the_excerpt_sits_on():
    """A citation pointing too early hides every error between it and the real line."""
    misplaced = output(evidence=[{
        "source": f"dlthub job runs logs {FAILED_RUN_ID} line {line_no(0)}",
        "excerpt": "requests.exceptions.HTTPError: 401 Client Error: Unauthorized",
    }])
    window = C.earliest_error_window(context(output=misplaced))
    assert window["located"] is True
    assert window["cited_line"] == line_no(0)
    assert window["anchor_line"] == line_no(8)
    assert line_no(3) in [candidate["line"] for candidate in window["candidates"]]
    assert "sits at line" in window["reason"]


def test_earliest_error_window_has_no_anchor_in_a_file_the_evaluator_does_not_hold():
    """A line of workspace code is no position in the run's log, so nothing can precede it."""
    in_code = output(evidence=[{"source": "pipelines/github.py line 42",
                                "excerpt": "raise HTTPError(response)"}])
    window = C.earliest_error_window(context(output=in_code))
    assert window["located"] is False
    assert window["candidates"] == []
    assert "not a log the evaluator holds" in window["reason"]


def test_finalize_reads_a_checks_array_the_judge_serialised_as_a_string():
    """Seen on a real run: `checks` came back as JSON text, so every answer read as missing."""
    prep = _prep_with()
    answers = [{"id": id, "kind": "judge", "outcome": "TRUE", "reasoning": "fine"}
               for id in C.judge_ids(prep.results)]
    final = C.finalize({"status": "succeeded", "summary": "done",
                        "checks": json.dumps(answers)}, prep)
    answered = [e for e in final["checks"] if e["kind"] == "judge"]
    assert answered and all(e["outcome"] == "TRUE" for e in answered)
    assert final["status"] == "succeeded"
    assert "could not be read" not in final["summary"]


def test_finalize_fails_loudly_when_the_judge_answers_cannot_be_read():
    """Silently reporting every judge check `N/A` hides a broken judge behind a pass rate."""
    prep = _prep_with()
    for broken in ("not json at all", {"id": "x"}, ["a", "b"]):
        final = C.finalize({"status": "succeeded", "summary": "done", "checks": broken}, prep)
        assert final["status"] == "failed", broken
        assert final["passed"] is False, broken
        assert "could not be read" in final["summary"], broken


def test_earliest_error_window_has_no_anchor_when_the_excerpt_is_not_in_the_log():
    """An invented excerpt with a line number used to anchor the search on that line."""
    invented = output(evidence=[{
        "source": f"dlthub job runs logs {FAILED_RUN_ID} line {line_no(9)}",
        "excerpt": "a phrase that appears nowhere in this log",
    }])
    window = C.earliest_error_window(context(output=invented))
    assert window["located"] is False
    assert window["anchor_line"] == 0
    assert window["cited_line"] == line_no(9)
    assert window["candidates"] == []


def test_earliest_error_window_has_no_anchor_for_a_misplaced_excerpt_it_cannot_locate():
    """A reworded excerpt matches the whole log on token overlap but sits on no single line."""
    reworded = output(evidence=[{
        "source": f"dlthub job runs logs {FAILED_RUN_ID} line {line_no(9)}",
        "excerpt": "401 Unauthorized extract started",
    }])
    placement = C.excerpt_placements(context(output=reworded))[0]
    assert placement["status"] == C.EXCERPT_MISPLACED and placement["found_line"] == 0

    window = C.earliest_error_window(context(output=reworded))
    assert window["located"] is False
    assert window["candidates"] == []
    assert "no anchor" in window["reason"]


def test_prepare_reports_a_transcript_it_could_not_read():
    """A parser that reads no call scores the same as an inspector that made none."""
    payload = {"type": "dlthub-platform:job-inspector", "status": "succeeded",
               "result": output(), "trace": trace()}
    unreadable = inspector_log(events=["  a shape the parser does not know"],
                               result_json=json.dumps(payload, indent=2))
    logs = {INSPECTOR_RUN_ID: unreadable, FAILED_RUN_ID: with_setup(FAILED_LOG)}
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID}, fetcher=fetcher(logs=logs))
    assert prep.ctx is not None and prep.ctx.transcript_unread is True
    assert prep.problems and "no tool call" in prep.problems[0]

    final = C.finalize({"status": "succeeded", "summary": "done", "checks": []}, prep)
    assert final["status"] == "failed"
    assert final["passed"] is False
    assert "could not read everything" in final["summary"]


def test_a_transcript_with_tool_calls_reports_no_problem():
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID}, fetcher=fetcher())
    assert prep.ctx is not None and prep.ctx.transcript_unread is False
    assert prep.problems == []


def test_an_evaluation_that_decided_nothing_does_not_pass():
    """`passed` true next to a pass rate of 0.0 reads as a clean run that graded nothing."""
    prep = _prep_with()
    prep.results.clear()
    final = C.finalize({"status": "succeeded", "summary": "done", "checks": []}, prep)
    assert final["pass_rate"] == 0.0
    assert final["passed"] is False
    assert "No check was decided" in final["summary"]
