"""Resolution, fetching, the judge inputs, and writing the computed results back."""

import json

from conftest import (
    DEPLOYED_RUN_TOOLS,
    FAILED_LOG,
    SETUP_NOISE,
    line_no,
    with_setup,
    FAILED_RUN_ID,
    INSPECTOR_RUN_ID,
    OLDER_RUN_ID,
    StubFetcher,
    context,
    deployed_run_log,
    deployed_run_trace,
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


def test_a_transcript_it_could_not_read_decides_nothing_about_what_the_inspector_did():
    """A blind parser used to score as an inspector that called nothing, and made it a pass."""
    aborted = output(status="aborted", classification="", confidence="", evidence=[])
    unreadable = context(output=aborted, inspector_log=inspector_log(
        events=["  a shape the parser does not know"]))
    assert unreadable.transcript_unread is True

    results, errors = C.run_deterministic(unreadable)
    assert errors == []
    assert results["aborted_without_investigation"].outcome == C.NA
    assert results["run_record_read"].outcome == C.NA
    assert "no tool call" in results["run_record_read"].reasoning

    readable = context()
    assert readable.transcript_unread is False
    assert C.run_deterministic(readable)[0]["run_record_read"].outcome == C.TRUE


def test_prepare_reads_the_tool_calls_a_deployed_run_printed():
    """A spoken block runs into the calls of its turn. Every call has to survive it."""
    payload = {"type": "dlthub-platform:job-inspector", "status": "succeeded",
               "result": output(), "trace": trace()}
    spoken = inspector_log(
        events=[
            "  says",
            "  I will read the run record before the logs.",
            f'  dlthub_get_run (dlt-workspace-mcp)  {{"run_id":"{FAILED_RUN_ID}"}}',
            f'  dlthub_get_run_logs (dlt-workspace-mcp)  {{"run_id":"{FAILED_RUN_ID}"}}',
        ],
        result_json=json.dumps(payload, indent=2),
    )
    logs = {INSPECTOR_RUN_ID: spoken, FAILED_RUN_ID: with_setup(FAILED_LOG)}
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID}, fetcher=fetcher(logs=logs))
    assert prep.ctx is not None
    assert [call.tool for call in prep.ctx.tool_calls] == [
        "dlthub_get_run", "dlthub_get_run_logs"
    ]
    assert prep.ctx.transcript_unread is False
    assert prep.problems == []
    assert prep.results["run_record_read"].outcome == C.TRUE


def test_prepare_hands_the_parser_the_tool_names_the_trace_records():
    """Verbosity 0 prints a bare name, and inside a spoken block only the trace settles it."""
    payload = {"type": "dlthub-platform:job-inspector", "status": "succeeded",
               "result": output(), "trace": trace()}
    blind = inspector_log(
        events=["  says", "  Reading the record.", "  dlthub_get_run (dlt-workspace-mcp)",
                "  Bash"],
        result_json=json.dumps(payload, indent=2),
    )
    logs = {INSPECTOR_RUN_ID: blind, FAILED_RUN_ID: with_setup(FAILED_LOG)}
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID}, fetcher=fetcher(logs=logs))
    assert prep.ctx is not None
    assert [call.tool for call in prep.ctx.tool_calls] == ["dlthub_get_run", "Bash"]


def test_finalize_reports_the_checks_the_pass_rate_left_out():
    """Without the tally, a rate over a third of the checks reads like one over all."""
    prep = _prep_with()
    judge = {"status": "succeeded", "summary": "done",
             "checks": [{"id": id, "kind": "judge", "outcome": "N/A", "reasoning": "no condition"}
                        for id in C.judge_ids(prep.results)]}
    final = C.finalize(judge, prep)

    outcomes = [entry["outcome"] for entry in final["checks"]]
    assert final["na_count"] == outcomes.count("N/A")
    assert final["decided_count"] == outcomes.count("TRUE") + outcomes.count("FALSE")
    assert final["na_count"] + final["decided_count"] == len(final["checks"])
    assert f"{final['na_count']} `N/A`" in final["summary"]
    assert f"over the {final['decided_count']} decided" in final["summary"]


def deployed_run_fetcher() -> StubFetcher:
    """The platform as it stood for the run in dlt-hub/dlthub-ai-workbench-internal#83."""
    job_ref = "jobs.jaffle_shop.load_jaffle_bad_config"
    payload = {"type": "dlthub-platform:job-inspector", "status": "succeeded",
               "result": output(classification="config"), "trace": deployed_run_trace()}
    return fetcher(
        logs={
            INSPECTOR_RUN_ID: deployed_run_log(result_json=json.dumps(payload, indent=2)),
            FAILED_RUN_ID: with_setup(FAILED_LOG),
        },
        records={
            INSPECTOR_RUN_ID: dict(INSPECTOR_RECORD, trigger=f"job.fail:{job_ref}"),
            EVALUATOR_RUN_ID: EVALUATOR_RECORD,
            FAILED_RUN_ID: failed_run(job_ref=job_ref),
        },
        runs_by_job={
            job_ref: [
                failed_run(job_ref=job_ref),
                {"id": OLDER_RUN_ID, "number": 11, "status": "succeeded",
                 "created_at": "2026-09-01T09:00:00Z"},
            ],
            "jobs.job_inspector": [INSPECTOR_RECORD],
        },
    )


def test_prepare_scores_what_a_deployed_run_did():
    """End to end over the captured run: its 11 calls reach the checks that read them.

    The parser read none of them before, so `transcript_unread` held all 18 transcript checks
    at `N/A` and a third of the evaluation measured nothing.
    """
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID}, fetcher=deployed_run_fetcher())
    assert prep.ctx is not None
    assert [call.tool for call in prep.ctx.tool_calls] == DEPLOYED_RUN_TOOLS
    assert prep.ctx.transcript_unread is False
    assert prep.ctx.transcript_blind is False
    assert prep.problems == []
    assert prep.errors == []

    reads_transcript = [entry.id for entry in C.CHECKS.values() if entry.reads_transcript]
    decided = {id for id in reads_transcript if prep.results[id].outcome != C.NA}
    assert len(decided) == 12, "the other six state a condition that did not apply"
    assert prep.results["run_record_read"].outcome == C.TRUE
    assert prep.results["run_logs_read"].outcome == C.TRUE
    assert prep.results["job_definition_read_for_config"].outcome == C.TRUE
    # the order of the calls survives the parse, which is what this one rests on
    assert prep.results["record_read_before_logs"].outcome == C.TRUE
    assert prep.results["single_run_scope"].outcome == C.TRUE


def test_a_deployed_run_reports_the_checks_it_left_undecided():
    """`pass_rate` alone says nothing about how much of the inspector was looked at."""
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID}, fetcher=deployed_run_fetcher())
    judge = {"status": "succeeded", "summary": "graded it",
             "checks": [{"id": id, "kind": "judge", "outcome": "TRUE", "reasoning": "fine"}
                        for id in C.judge_ids(prep.results)]}
    final = C.finalize(judge, prep)

    assert final["status"] == "succeeded"
    assert final["passed"] is True
    assert final["decided_count"] + final["na_count"] == len(final["checks"])
    assert final["na_count"] > 0
    assert f"{final['na_count']} `N/A`" in final["summary"]
    assert f"over the {final['decided_count']} decided" in final["summary"]
