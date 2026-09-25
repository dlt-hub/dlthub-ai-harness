"""Resolution, fetching, the judge inputs, and writing the computed results back."""

import asyncio
import json
from datetime import datetime, timezone

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
    "status": "completed",
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
    assert [call.tool for call in ctx.tool_calls] == ["dlthub_get_run", "dlthub_get_run_logs",
                                                      "dlthub_get_job", "Read"]


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


def test_earliest_error_window_anchors_on_the_real_line_when_the_citation_is_a_little_late():
    """A citation two lines late is within tolerance, so the excerpt counts as cited at its line;
    the anchor is still where the text sits, or the exception itself would read as an error
    the inspector skipped."""
    late = output(evidence=[{
        "source": f"dlthub job runs logs {FAILED_RUN_ID} line {line_no(10)}",
        "excerpt": "requests.exceptions.HTTPError: 401 Client Error: Unauthorized",
        "provenance": "run_log",
    }])
    ctx = context(output=late)
    assert C.excerpt_placements(ctx)[0]["status"] == C.EXCERPT_AT_CITED
    window = C.earliest_error_window(ctx)
    assert window["located"] is True
    assert window["anchor_line"] == line_no(8)
    assert line_no(8) not in [candidate["line"] for candidate in window["candidates"]]


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
    # the run read `jaffle_shop/bad_config.py`, so that is the file its failed log names
    failed_log = [
        line.replace("/workspace/pipelines/github.py", "/workspace/jaffle_shop/bad_config.py")
        for line in FAILED_LOG
    ]
    return fetcher(
        logs={
            INSPECTOR_RUN_ID: deployed_run_log(result_json=json.dumps(payload, indent=2)),
            FAILED_RUN_ID: with_setup(failed_log),
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

    The parser read none of them before, so `transcript_unread` held all 17 transcript checks
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
    assert len(decided) == 13, "the other seven state a condition that did not apply"
    assert prep.results["job_declaration_read"].outcome == C.TRUE
    assert prep.results["run_record_read"].outcome == C.TRUE
    # its one `Read` opened the file the traceback names
    assert prep.results["workspace_file_read_when_referenced"].outcome == C.TRUE
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


# the summary


def _all_true(prep):
    return [{"id": id, "kind": "judge", "outcome": "TRUE", "reasoning": "fine"}
            for id in C.judge_ids(prep.results)]


def test_finalize_opens_with_the_findings_and_names_each_broken_instruction():
    """A reader acts on the summary without opening the rubric."""
    prep = _prep_with(output=output(fix_target="", fix_change="", open_points=[]))
    final = C.finalize({"status": "succeeded", "summary": "The judge speaks here.",
                        "checks": _all_true(prep)}, prep)
    summary = final["summary"]
    assert summary.startswith("## Findings\n")
    assert "## Findings\n\n- The inspector broke " in summary
    assert "Verdict" not in summary
    assert "- Broken: " in summary
    assert "(`fix_names_target_and_change`)" in summary
    assert C.instruction_of("fix_names_target_and_change") in summary
    assert prep.results["fix_names_target_and_change"].reasoning in summary
    # the judge's own words follow the findings, then the sections in order
    assert summary.index("The judge speaks here.") > summary.index("The inspector broke ")
    for heading in ("## Scope", "## Detailed evaluation results"):
        assert heading in summary
    assert (summary.index("- Instruction following: ") < summary.index("- Quality: ")
            < summary.index("## Scope")
            < summary.index("## Detailed evaluation results"))
    assert summary.index("check results:") > summary.index("## Detailed evaluation results")


def test_finalize_says_so_plainly_when_nothing_is_false():
    prep = _prep_with()
    final = C.finalize({"status": "succeeded", "summary": "", "checks": _all_true(prep)}, prep)
    assert final["passed"] is True
    assert "## Findings\n\n- The inspector followed all " in final["summary"]
    assert "- Broken: " not in final["summary"]
    assert "- Instruction following: no findings. " in final["summary"]
    assert "- Quality: no findings. " in final["summary"]


def test_finalize_says_the_evaluation_was_incomplete_when_a_judge_check_went_unanswered():
    prep = _prep_with()
    final = C.finalize({"status": "succeeded", "summary": "", "checks": _all_true(prep)[:-1]},
                       prep)
    assert "could not grade everything" in final["summary"]
    assert "went unanswered" in final["summary"]
    assert final["passed"] is False


def test_the_summary_names_a_security_finding_first():
    checks = [
        {"id": "no_write_tool_used", "kind": "deterministic", "outcome": "FALSE",
         "reasoning": "tool call 3 called the write tool 'Edit'"},
        {"id": "summary_within_length", "kind": "deterministic", "outcome": "FALSE",
         "reasoning": "the summary runs to 4000 characters"},
        {"id": "run_record_read", "kind": "deterministic", "outcome": "TRUE",
         "reasoning": "read it"},
    ]
    found = C.findings_bullets([{"checks": checks, "inspector_run_id": "run-1"}])
    assert found[0].startswith(
        "The inspector broke 2 of the 3 decided checks on run `run-1`"
    )
    # the id is linked when the section is rendered; see the linkify tests below
    assert found[1].startswith("A security rule was broken: ")
    bullets = C.category_bullets([{"checks": checks}], C.INSTRUCTION_FOLLOWING,
                                 C.category_verdict(checks))
    assert bullets[0].startswith("Instruction following: blocking. ")
    # the broken instructions are nested under the category bullet
    assert bullets[1][0].startswith("Security rule broken: ")
    assert "`no_write_tool_used`" in bullets[1][0]


def test_category_verdict_reads_its_own_checks():
    def entries(*outcomes):
        return [{"id": id, "kind": "deterministic", "outcome": outcome, "reasoning": ""}
                for id, outcome in outcomes]

    def band(false_count, decided):
        """`decided` checks of which `false_count` broke, none of them a security rule."""
        return C.category_verdict([
            {"id": f"check_{index}", "kind": "deterministic", "reasoning": "",
             "outcome": "FALSE" if index < false_count else "TRUE"}
            for index in range(decided)
        ])

    assert C.category_verdict(entries(("run_record_read", "N/A"))) == C.NOT_GRADED
    assert C.category_verdict(entries(("run_record_read", "TRUE"))) == C.NO_FINDINGS
    # the share of the decided checks that broke picks the band
    assert band(1, 400) == C.MINOR_ISSUES      # 0.25%
    assert band(7, 400) == C.MINOR_ISSUES      # 1.75%, under the band
    assert band(8, 400) == C.NEEDS_ATTENTION   # 2% exactly, the band opens
    assert band(40, 400) == C.NEEDS_ATTENTION  # 10% exactly
    assert band(41, 400) == C.BLOCKING         # over 10%
    assert band(1, 4) == C.BLOCKING            # a small denominator is not a free pass
    # a security FALSE is blocking whatever the share
    assert C.category_verdict(entries(
        ("no_data_access", "FALSE"), ("run_logs_read", "TRUE"),
        ("skill_loaded", "TRUE"), ("summary_within_length", "TRUE"),
    )) == C.BLOCKING


def test_the_results_table_carries_every_check_and_survives_the_ui():
    prep = _prep_with()
    final = C.finalize({"status": "succeeded", "summary": "", "checks": _all_true(prep)}, prep)
    summary = final["summary"]
    assert "| check_id | category | kind | results | reasoning |" in summary
    # the category's verdict is one thing about the category, not a fact about each row
    assert "category_verdict" not in summary
    rows = [line for line in summary.splitlines() if line.startswith("| `")]
    # a check that decided nothing measured nothing: the tally counts it, the table omits it
    decided = [entry for entry in final["checks"] if entry["outcome"] != "N/A"]
    assert len(rows) == len(decided) < len(C.CHECKS)
    assert not [row for row in rows if "| N/A |" in row]
    for row in rows:
        assert row.count("|") == 6, row
    # a reasoning that quotes a log line must not open a code span the row never closes
    assert C._cell("read `pipelines/github.py") == "read 'pipelines/github.py"
    assert C._cell("a | b") == "a \\| b"
    assert summary.count("`") % 2 == 0


def test_one_run_recommends_nothing_whatever_the_judge_writes():
    """One run is one observation. What to change in the instructions rests on the window."""
    prep = _prep_with()
    judge = {"status": "succeeded", "summary": "", "checks": _all_true(prep),
             "recommendation": "Tell the inspector to open the file the traceback names."}
    final = C.finalize(judge, prep)
    assert final["recommendation"] == ""
    assert judge["recommendation"] not in final["summary"]
    assert "## Recommendation" not in final["summary"]


def test_instruction_of_is_the_first_paragraph_of_the_docstring():
    assert C.instruction_of("run_record_read") == "The run record of the inspected run was read."
    assert C.instruction_of("fix_actionable").startswith("`proposed_fix` names the concrete")
    assert C.instruction_of("not_a_check") == "not_a_check"


def test_judge_windows_carry_the_summary_sections_and_the_leads():
    prep = C.prepare({"run_id": EVALUATOR_RUN_ID}, fetcher=fetcher())
    windows = json.loads(prep.judge_inputs["evidence_windows"])
    assert [s["title"] for s in windows["summary_sections"]] == list(C.REQUIRED_SUMMARY_SECTIONS)
    assert windows["summary_sections"][0]["bullets"]
    assert windows["summary_preamble"] == []
    assert windows["dependency_symptoms"] == []
    assert windows["workspace_files_referenced"][0]["file"].endswith("pipelines/github.py")
    assert windows["files_read"][0]["tool"] == "Read"
    assert windows["other_runs_read"] == []
    assert windows["open_point_reasons"] == []
    assert json.loads(prep.judge_inputs["inspector_output"])["open_points"]


# the batch window


SECOND_RUN_ID = "66666666-6666-4666-8666-666666666666"
WINDOW_END = datetime(2026, 9, 2, tzinfo=timezone.utc)


def week_fetcher(**overrides):
    """Three inspector runs: two inside the window, one a fortnight old."""
    second = dict(INSPECTOR_RECORD, id=SECOND_RUN_ID, created_at="2026-08-31T10:05:00Z")
    stale = dict(INSPECTOR_RECORD, id=OLDER_RUN_ID, created_at="2026-08-15T10:05:00Z")
    records = {
        INSPECTOR_RUN_ID: INSPECTOR_RECORD,
        SECOND_RUN_ID: second,
        OLDER_RUN_ID: stale,
        FAILED_RUN_ID: failed_run(),
    }
    logs = {INSPECTOR_RUN_ID: envelope_log(), SECOND_RUN_ID: envelope_log(),
            OLDER_RUN_ID: envelope_log(), FAILED_RUN_ID: with_setup(FAILED_LOG)}
    runs_by_job = {
        "jobs.job_inspector": [INSPECTOR_RECORD, second, stale],
        "pipelines.github_events": [failed_run()],
    }
    kwargs = {"records": records, "logs": logs, "runs_by_job": runs_by_job}
    kwargs.update(overrides)
    return StubFetcher(**kwargs)


def test_the_window_holds_the_runs_of_the_week_and_leaves_the_older_ones_out():
    batch = C.prepare_batch({"run_id": "local", "trigger": "schedule:0 7 * * 1"},
                            fetcher=week_fetcher(), inspector_job_ref="jobs.job_inspector",
                            until=WINDOW_END)
    assert batch.aborted is False
    assert batch.found == 2
    assert [prep.inspector_run_id for prep in batch.preps] == [INSPECTOR_RUN_ID, SECOND_RUN_ID]
    assert batch.window["since"] == "2026-08-26T00:00:00+00:00"
    assert batch.window["until"] == "2026-09-02T00:00:00+00:00"
    assert batch.window["runs_evaluated"] == 2
    assert batch.capped is False


def test_a_run_that_is_still_going_is_skipped_with_the_reason():
    running = dict(INSPECTOR_RECORD, id=SECOND_RUN_ID, status="running",
                   created_at="2026-08-31T10:05:00Z")
    source = week_fetcher()
    source.records[SECOND_RUN_ID] = running
    source.runs_by_job["jobs.job_inspector"] = [INSPECTOR_RECORD, running]
    batch = C.prepare_batch({"run_id": "local"}, fetcher=source,
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    assert [prep.inspector_run_id for prep in batch.preps] == [INSPECTOR_RUN_ID]
    assert batch.skipped == [
        {"run_id": SECOND_RUN_ID, "reason": "the run is running and has not finished"}
    ]

    # a run the platform stopped never produced a result either
    cancelled = dict(INSPECTOR_RECORD, id=SECOND_RUN_ID, status="cancelled",
                     created_at="2026-08-31T10:05:00Z")
    source.records[SECOND_RUN_ID] = cancelled
    source.runs_by_job["jobs.job_inspector"] = [INSPECTOR_RECORD, cancelled]
    batch = C.prepare_batch({"run_id": "local"}, fetcher=source,
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    assert batch.skipped[0]["reason"] == "the run is cancelled, so it never produced a result"


def test_a_run_the_platform_calls_completed_is_graded():
    """The run record says `completed`; only the agent's own result says `succeeded`."""
    assert "completed" in C.GRADED_RUN_STATUSES
    batch = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    assert [prep.inspector_run_id for prep in batch.preps] == [INSPECTOR_RUN_ID, SECOND_RUN_ID]
    assert batch.skipped == []


def test_a_run_that_declared_no_result_is_skipped_rather_than_dropped():
    source = week_fetcher()
    source.logs[SECOND_RUN_ID] = inspector_log(result_json=None)
    batch = C.prepare_batch({"run_id": "local"}, fetcher=source,
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    assert [prep.inspector_run_id for prep in batch.preps] == [INSPECTOR_RUN_ID]
    assert batch.skipped[0]["run_id"] == SECOND_RUN_ID
    assert "declared no result" in batch.skipped[0]["reason"]
    assert batch.found == len(batch.preps) + len(batch.skipped)


def test_the_cap_says_it_cut_the_window_short():
    batch = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END,
                            max_runs=1)
    assert batch.capped is True
    assert batch.found == 1
    assert "more than the" in C.render_batch_summary([], batch, batch.skipped) or batch.capped


def test_a_batch_job_with_no_job_ref_aborts_and_says_what_to_pass():
    batch = C.prepare_batch({"run_id": "local", "trigger": "schedule:0 7 * * 1"},
                            fetcher=week_fetcher(), until=WINDOW_END)
    assert batch.aborted is True
    assert "inspector_job_ref" in batch.abort_reason
    assert batch.aborted_output["status"] == "aborted"
    assert batch.aborted_output["window"]["runs_found"] == 0


def test_finalize_batch_reports_the_window_the_counts_and_every_run():
    batch = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    evaluations = [
        C.finalize({"status": "succeeded", "summary": "", "checks": _all_true(prep)}, prep)
        for prep in batch.preps
    ]
    final = C.finalize_batch(evaluations, batch)
    assert final["window"]["runs_found"] == 2
    assert final["window"]["runs_evaluated"] == 2
    assert [entry["inspector_run_id"] for entry in final["evaluations"]] == [
        INSPECTOR_RUN_ID, SECOND_RUN_ID
    ]
    summary = final["summary"]
    for heading in ("- Instruction following: ", "- Quality: ",
                    "## Recommendation", "## Detailed evaluation results"):
        assert heading in summary
    assert "2026-08-26T00:00:00+00:00 to 2026-09-02T00:00:00+00:00" in summary
    assert f"`{INSPECTOR_RUN_ID}`" in summary
    assert final["decided_count"] == sum(e["decided_count"] for e in evaluations)


def test_finalize_batch_counts_a_check_over_the_runs_it_broke_on():
    batch = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    evaluations = []
    for index, prep in enumerate(batch.preps):
        final = C.finalize({"status": "succeeded", "summary": "", "checks": _all_true(prep)},
                           prep)
        if index == 0:
            for entry in final["checks"]:
                if entry["id"] == "no_data_access":
                    entry["outcome"] = "FALSE"
                    entry["reasoning"] = "the inspector queried the destination"
        evaluations.append(final)
    final = C.finalize_batch(evaluations, batch)
    assert final["passed"] is False
    assert final["evaluations"][0]["false_checks"] == ["no_data_access"]
    # one form wherever a count over runs is reported, and a header saying what it counts
    assert "FALSE 1/2" in final["summary"]
    assert "| results | reasoning (from FALSE runs if applicable) |" in final["summary"]
    # a check that broke nowhere carries no reasoning: one run's answer is not the window's
    passing = [row for row in final["summary"].splitlines()
               if row.startswith("| `succeeded_has_evidence`")]
    assert passing and passing[0].endswith("| TRUE 2/2 | - |"), passing
    assert C.outcome_over_runs({"false": 0, "decided": 7}) == "TRUE 7/7"
    assert C.outcome_over_runs({"false": 0, "decided": 0}) == "N/A"
    assert "Security rule broken: " in final["summary"]
    counts = C.check_counts(evaluations)
    assert counts["no_data_access"] == {"false": 1, "decided": 2}


def test_the_window_recommendation_is_asked_for_once_over_every_run():
    batch = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    evaluations = []
    for prep in batch.preps:
        final = C.finalize({"status": "succeeded", "summary": "", "checks": _all_true(prep)},
                           prep)
        for entry in final["checks"]:
            if entry["id"] == "evidence_cited_at_line":
                entry["outcome"] = "FALSE"
                entry["reasoning"] = "evidence[0] cites line 49, the excerpt sits at 54"
        evaluations.append(final)

    findings = json.loads(C.window_findings(evaluations, batch)["window_findings"])
    assert findings["runs_evaluated"] == 2
    broken = findings["broken_checks"]
    assert [entry["check_id"] for entry in broken] == ["evidence_cited_at_line"]
    assert broken[0] == {
        "check_id": "evidence_cited_at_line",
        "category": "Instruction following",
        "instruction": C.instruction_of("evidence_cited_at_line"),
        "runs_broken": 2,
        "runs_decided": 2,
        "reasonings": ["evidence[0] cites line 49, the excerpt sits at 54."] * 2,
    }

    # a judge that names a section and forgets the file gets the file put back
    written = "In `Investigate`, require the cited line to hold the quoted excerpt."
    final = C.finalize_batch(evaluations, batch, recommendation=written)
    named = (f"In `{C.INSPECTOR_DEFINITION_PATH}`, in `Investigate`, require the cited line"
             " to hold the quoted excerpt.")
    assert named in final["summary"]
    assert final["recommendation"] == f"- {named}"
    # one that names it already is left alone
    assert C.name_the_file(named) == named


def test_a_window_with_nothing_broken_asks_for_no_recommendation():
    """The pass costs a loop run, so a clean window does not make it."""
    class Loop:
        def __init__(self):
            self.calls = 0

        async def run(self, inputs):
            self.calls += 1
            return {"recommendation": "never reached"}

    batch = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    evaluations = [
        C.finalize({"status": "succeeded", "summary": "", "checks": _all_true(prep)}, prep)
        for prep in batch.preps
    ]
    loop = Loop()
    written = asyncio.run(C.judge_window_recommendation(loop, evaluations, batch))
    assert (written, loop.calls) == ("", 0)

    final = C.finalize_batch(evaluations, batch)
    assert "## Recommendation" in final["summary"]
    assert "No change to the inspector's instructions follows" in final["summary"]


def test_a_judge_run_that_raised_is_reported_as_a_skipped_run():
    batch = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    evaluations = [
        C.finalize({"status": "succeeded", "summary": "", "checks": _all_true(batch.preps[0])},
                   batch.preps[0])
    ]
    failures = [{"run_id": SECOND_RUN_ID, "reason": "AgentRunFailed: the loop hit its token limit"}]
    final = C.finalize_batch(evaluations, batch, failures)
    assert final["window"]["runs_skipped"] == 1
    assert final["skipped_runs"] == failures
    assert "token limit" in final["summary"]
    assert final["passed"] is False


def test_the_sdk_walk_stops_at_the_edge_of_the_window():
    """The listing carries no time filter, so the walk is what bounds the window."""

    class _Run:
        def __init__(self, record):
            self.record = record

        def to_dict(self):
            return self.record

    class _Runs:
        def __init__(self, records):
            self.records = records
            self.read = 0

        def list(self, limit=None):
            for record in self.records:
                self.read += 1
                yield _Run(record)

    class _Job:
        def __init__(self, runs):
            self.runs = runs

    class _Jobs:
        def __init__(self, job):
            self.job = job

        def get(self, ref):
            return self.job

    class _Workspace:
        def __init__(self, records):
            self.runs = _Runs(records)
            self.jobs = _Jobs(_Job(self.runs))

    records = [
        {"id": "a", "created_at": "2026-09-01T00:00:00Z"},
        {"id": "b", "created_at": "2026-08-30T00:00:00Z"},
        {"id": "c", "created_at": "2026-08-01T00:00:00Z"},
        {"id": "d", "created_at": "2026-07-01T00:00:00Z"},
    ]
    workspace = _Workspace(records)
    runs, capped = C.SdkFetcher(workspace).job_runs_since(
        "jobs.job_inspector", datetime(2026, 8, 26, tzinfo=timezone.utc)
    )
    assert [run["id"] for run in runs] == ["a", "b"]
    assert capped is False
    assert workspace.runs.read == 3  # the walk stopped on the first run outside the window

    runs, capped = C.SdkFetcher(_Workspace(records)).job_runs_since(
        "jobs.job_inspector", datetime(2026, 7, 1, tzinfo=timezone.utc), cap=2
    )
    assert [run["id"] for run in runs] == ["a", "b"]
    assert capped is True


def test_the_batch_deployment_function_reports_the_window_the_way_the_readme_declares_it():
    """The loop drives one judge run per prepared evaluation, and one failure costs one run."""
    import asyncio

    class _Loop:
        """Answers every open check TRUE, and raises on the second run."""

        def __init__(self):
            self.runs = 0

        async def run(self, inputs):
            self.runs += 1
            if self.runs == 2:
                raise RuntimeError("the loop hit its token limit")
            open_checks = json.loads(inputs["evidence_windows"])["open_checks"]
            return {"status": "succeeded", "summary": "graded", "recommendation": "none",
                    "checks": [{"id": id, "kind": "judge", "outcome": "TRUE",
                                "reasoning": "fine"} for id in open_checks]}

    loop = _Loop()
    run_context = {"run_id": "local", "ai_loop": loop}

    async def batch_job():
        batch = C.prepare_batch(run_context, fetcher=week_fetcher(),
                                inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
        assert batch.aborted is False
        evaluations, failures = [], []
        for prep in batch.preps:
            try:
                output = await run_context["ai_loop"].run(inputs=prep.judge_inputs)
            except Exception as ex:
                failures.append({"run_id": prep.inspector_run_id,
                                 "reason": f"{type(ex).__name__}: {ex}"})
                continue
            evaluations.append(C.finalize(output, prep))
        return C.finalize_batch(evaluations, batch, failures)

    final = asyncio.run(batch_job())
    assert loop.runs == 2
    assert final["status"] == "succeeded"
    assert final["window"]["runs_found"] == 2
    assert final["window"]["runs_evaluated"] == 1
    assert final["window"]["runs_skipped"] == 1
    assert final["skipped_runs"][0]["run_id"] == SECOND_RUN_ID
    assert "token limit" in final["summary"]
    assert final["passed"] is False  # a run that was found and not graded fails the week


def test_a_window_that_graded_nothing_says_so_instead_of_printing_an_empty_table():
    batch = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector",
                            until=datetime(2026, 9, 24, tzinfo=timezone.utc))
    final = C.finalize_batch([], batch)
    assert batch.found == 0
    assert "| inspector_run_id |" not in final["summary"]
    assert "nothing to tabulate" in final["summary"]


def test_a_skip_reason_does_not_repeat_the_run_id_the_row_carries():
    entry = {"run_id": "abc", "reason": "inspector run abc declared no result: nothing to read"}
    assert C._skip_reason(entry) == "declared no result: nothing to read"
    assert C._skip_reason({"run_id": "abc", "reason": "the run is running"}) == "the run is running"


# where the window starts


def history(*entries):
    """Deployments newest first: (version, ISO timestamp, definition hash)."""
    return [{"version": v, "created_at": at, "content_hash": h} for v, at, h in entries]


def test_the_window_starts_at_the_deployment_that_last_changed_the_definition():
    walked = history(
        (26, "2026-09-24T14:48:12Z", "new"),
        (25, "2026-09-24T14:33:08Z", "old"),
    )
    moment, reason = C.definition_changed_at(walked)
    assert moment == datetime(2026, 9, 24, 14, 48, 12, tzinfo=timezone.utc)
    assert "workspace deployment 26, the deploy that last changed" in reason


def test_a_definition_carried_by_several_deployments_reaches_back_to_the_first_of_them():
    walked = history(
        (26, "2026-09-24T14:48:12Z", "same"),
        (25, "2026-09-24T14:33:08Z", "same"),
        (24, "2026-09-24T14:31:16Z", "older"),
    )
    moment, reason = C.definition_changed_at(walked)
    assert moment == datetime(2026, 9, 24, 14, 33, 8, tzinfo=timezone.utc)
    assert "workspace deployment 25, the deploy that last changed" in reason


def test_a_definition_that_never_changed_reaches_back_to_the_oldest_deployment_read():
    walked = history((3, "2026-09-01T00:00:00Z", "same"), (2, "2026-08-01T00:00:00Z", "same"))
    moment, reason = C.definition_changed_at(walked)
    assert moment == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert "unchanged across the 2 workspace deployment(s) read" in reason


def test_a_deployment_that_did_not_hold_the_definition_counts_as_a_change():
    walked = history((9, "2026-09-02T00:00:00Z", "first"), (8, "2026-09-01T00:00:00Z", ""))
    moment, _ = C.definition_changed_at(walked)
    assert moment == datetime(2026, 9, 2, tzinfo=timezone.utc)


def test_no_deployment_history_leaves_the_window_to_the_dated_fallback():
    assert C.definition_changed_at([]) == (None, "")
    since, until, source = C.resolve_window(
        week_fetcher(), until=WINDOW_END, window_days=7
    )
    assert since == datetime(2026, 8, 26, tzinfo=timezone.utc)
    assert "falls back to the 7 days" in source


def test_a_given_since_wins_over_the_deployment_history():
    given = datetime(2026, 9, 1, tzinfo=timezone.utc)
    since, _, source = C.resolve_window(week_fetcher(), since=given, until=WINDOW_END)
    assert since == given
    assert source == "the `since` this run was given"


class _HistoryFetcher(StubFetcher):
    def __init__(self, walked, **kwargs):
        super().__init__(**kwargs)
        self.walked = walked

    def deployment_history(self, path, cap=C.DEFAULT_DEPLOYMENT_WALK):
        return self.walked[:cap]


def test_the_batch_window_starts_at_the_definition_change_and_says_so():
    source = _HistoryFetcher(
        history((26, "2026-09-01T00:00:00Z", "new"), (25, "2026-08-20T00:00:00Z", "old")),
        records=week_fetcher().records, logs=week_fetcher().logs,
        runs_by_job=week_fetcher().runs_by_job,
    )
    batch = C.prepare_batch({"run_id": "local"}, fetcher=source,
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    assert batch.since == datetime(2026, 9, 1, tzinfo=timezone.utc)
    # the run of the older definition is outside the window
    assert [prep.inspector_run_id for prep in batch.preps] == [INSPECTOR_RUN_ID]
    assert "workspace deployment 26, the deploy that last changed" in batch.window["since_is"]
    final = C.finalize_batch([], batch)
    assert ("The window starts where workspace deployment 26, the deploy that last changed"
            in final["summary"])


def test_an_empty_window_is_a_quiet_result_and_a_graded_nothing_is_a_fault():
    """The deployment function raises on one and completes on the other."""
    quiet = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector",
                            until=datetime(2026, 9, 24, tzinfo=timezone.utc))
    assert quiet.found == 0
    assert C.finalize_batch([], quiet)["status"] == "succeeded"

    source = week_fetcher()
    source.logs[INSPECTOR_RUN_ID] = inspector_log(result_json=None)
    source.logs[SECOND_RUN_ID] = inspector_log(result_json=None)
    faulty = C.prepare_batch({"run_id": "local"}, fetcher=source,
                             inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    assert faulty.found == 2 and faulty.preps == []
    assert C.finalize_batch([], faulty)["status"] == "failed"


# the shape every background agent's summary takes


def assert_summary_shape(summary, sections):
    """Headings over short bullets: nothing before the first, nothing outside a bullet.

    `sections` carries the heading markers, so a subsection reads `### Quality`. A markdown
    table is allowed as the last thing in the last section, and nowhere else.
    """
    lines = summary.splitlines()
    assert lines[0].startswith("## "), lines[0]
    assert [line for line in lines if line.startswith("#")] == sections
    seen_table = False
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("#"):
            assert not seen_table, f"a heading follows the table: {line}"
            continue
        if line.startswith("|"):
            seen_table = True
            continue
        assert not seen_table, f"a bullet follows the table: {line}"
        assert line.startswith(("- ", "  - ")), f"line outside a bullet: {line}"
    assert summary.count("`") % 2 == 0, "an unbalanced code span"
    assert "\\`" not in summary, "an escaped backtick breaks the span it sits in"
    # the renderer strips raw HTML, so a tag in the summary is a section the reader loses
    assert "<" not in summary, "raw HTML in the summary"


def test_one_evaluation_takes_the_shape():
    prep = _prep_with(output=output(fix_target="", fix_change="", open_points=[]))
    final = C.finalize(
        {"status": "succeeded", "summary": "It missed the file. The cause stands anyway.",
         "recommendation": "Add a rule under Investigate.", "checks": _all_true(prep)},
        prep,
    )
    assert_summary_shape(
        final["summary"],
        ["## Findings", "## Scope", "## Detailed evaluation results"],
    )


def test_a_window_takes_the_same_shape():
    batch = C.prepare_batch({"run_id": "local"}, fetcher=week_fetcher(),
                            inspector_job_ref="jobs.job_inspector", until=WINDOW_END)
    evaluations = [
        C.finalize({"status": "succeeded", "summary": "", "recommendation": "Add a rule.",
                    "checks": _all_true(prep)}, prep)
        for prep in batch.preps
    ]
    final = C.finalize_batch(evaluations, batch,
                             [{"run_id": "x", "reason": "the run is running"}])
    assert_summary_shape(
        final["summary"],
["## Findings", "## Recommendation", "## Scope",
         "## Detailed evaluation results"],
    )


def test_a_judge_paragraph_becomes_bullets():
    assert C.as_bullets("One thing happened. Another followed.") == [
        "One thing happened.", "Another followed."
    ]
    assert C.as_bullets("- already a bullet\n- and another") == [
        "already a bullet", "and another"
    ]
    # a heading inside a prose field would open a section the renderer does not own
    assert C.as_bullets("## Diagnosis\n- the cause") == ["the cause"]


def test_every_run_id_and_job_ref_in_the_summary_is_a_link():
    links = ("https://app.example", "ws-1")
    text = "run 11111111-1111-4111-8111-111111111111 of `jobs.a.b` failed"
    linked = C.linkify(text, links)
    assert "[`11111111-1111-4111-8111-111111111111`](https://app.example/w/ws-1/runs/" in linked
    assert "[`jobs.a.b`](https://app.example/w/ws-1/jobs/jobs.a.b)" in linked

    # a link already written is left alone, target and all
    once = C.linkify(linked, links)
    assert once == linked

    # without a workspace the text stands as it was
    assert C.linkify(text) == text


def test_the_rendered_summary_links_the_ids_the_checks_wrote():
    prep = _prep_with()
    prep.links = ("https://app.example", "ws-1")
    final = C.finalize({"status": "succeeded", "summary": "", "checks": _all_true(prep)}, prep)
    summary = final["summary"]
    assert f"[`{INSPECTOR_RUN_ID}`](https://app.example/w/ws-1/runs/{INSPECTOR_RUN_ID})" in summary
    # a reasoning that names the inspected run carries the link too
    assert summary.count(f"/runs/{FAILED_RUN_ID}") > 1
    assert_summary_shape(
        summary,
        ["## Findings", "## Scope", "## Detailed evaluation results"],
    )
