"""Real inspector runs, captured with `capture` and replayed with `FileFetcher`.

Each directory under `fixtures/captured/` holds what one evaluation read: the inspector run
and its log, the stored result and trace, the inspected run and its log, the job's run
list, the pipeline trace when there was one. The runs came from a pydantic-ai loop on an
Azure deployment. Four ran an inspector definition that predates the provenance, fix and
summary rules, so they show what those rules catch on a transcript the launcher printed.
Five ran the current definition; the third summary heading of the first three was captured
as `Caveats` and renamed to `Confidence` in the fixture when the definition renamed the
section. The last two ran on the platform runner and show what the tag and fix-target rules
catch.
"""

import glob
import json
import os
from pathlib import Path

import pytest

import checks as C

CAPTURED = Path(__file__).parent / "fixtures" / "captured"
CASES = sorted(entry.name for entry in CAPTURED.iterdir() if entry.is_dir())
CURRENT_DEFINITION = ("config_missing_destination_type",
                      "config_missing_destination_type_value_open",
                      "dependency_followed_to_producer",
                      "dq_launched_by_tag_without_producer",
                      "cursor_value_from_a_comment")
"""Runs of the definition that carries the provenance, fix and summary rules."""
CLEAN = CURRENT_DEFINITION[:2]
"""The runs among them with no deterministic FALSE beyond two rules added after they ran:
their Recommendation opens with "Ask a coding agent to" (`recommendation_is_the_action`) and
chains a second action onto the first with a comma (`recommendation_one_action_per_bullet`)."""
EARLIER_DEFINITION = tuple(name for name in CASES if name not in CURRENT_DEFINITION)


def replay(name: str) -> C.EvalPrep:
    directory = CAPTURED / name
    run_id = os.path.basename(glob.glob(str(directory / "results" / "*.json"))[0])[:-5]
    return C.prepare({"run_id": "local"}, fetcher=C.FileFetcher(str(directory)),
                     inspector_run_id=run_id)


def outcome(prep: C.EvalPrep, check_id: str) -> str:
    return prep.results[check_id].outcome


@pytest.mark.parametrize("name", CASES)
def test_every_capture_replays_without_a_parser_fault(name):
    prep = replay(name)
    assert prep.aborted is False, prep.abort_reason
    assert prep.errors == []
    assert prep.problems == []
    ctx = prep.ctx
    # the transcript parser reads every tool the trace recorded; the trace lists local tools
    # before MCP tools, so the comparison is by set
    assert {call.tool for call in ctx.tool_calls} == set(ctx.tools_recorded)
    assert ctx.transcript_blind is False


def _finalized(name):
    prep = replay(name)
    answers = [{"id": id, "kind": "judge", "outcome": "N/A", "reasoning": "not judged here"}
               for id in C.judge_ids(prep.results)]
    return C.finalize({"status": "succeeded", "summary": "", "checks": answers}, prep)


@pytest.mark.parametrize("name", EARLIER_DEFINITION)
def test_the_summary_lists_each_broken_instruction_in_words(name):
    final = _finalized(name)
    broken = [entry["id"] for entry in final["checks"] if entry["outcome"] == C.FALSE]
    assert broken, "a run of the earlier definition breaks at least one of the new rules"
    assert final["summary"].startswith("## Findings\n")
    assert "## Findings\n\n- The inspector broke " in final["summary"]
    for check_id in broken:
        assert f"(`{check_id}`)" in final["summary"]
        assert C.instruction_of(check_id) in final["summary"]


@pytest.mark.parametrize("name", CLEAN)
def test_a_run_of_the_current_definition_passes_the_deterministic_layer(name):
    final = _finalized(name)
    false = [entry["id"] for entry in final["checks"] if entry["outcome"] == C.FALSE]
    assert false == ["recommendation_one_action_per_bullet", "recommendation_is_the_action"]
    wrapper = next(entry for entry in final["checks"] if entry["id"] == false[1])
    assert "coding agent" in wrapper["reasoning"].lower()
    chained = next(entry for entry in final["checks"] if entry["id"] == false[0])
    assert "chains a second action" in chained["reasoning"]


def test_a_data_quality_job_whose_input_was_never_loaded():
    """`jaffle_shop_dq` raised `DataQualityFailed: table(s) ['orders'] were not loaded`.

    The inspector read the run list, the record and the log, classified `upstream_data` and
    told the reader to inspect a source configuration it never opened.
    """
    prep = replay("dq_missing_input")
    ctx = prep.ctx
    assert ctx.classification == "upstream_data"
    assert [call.tool for call in ctx.tool_calls] == [
        "dlthub_list_runs", "dlthub_get_run", "dlthub_get_run_logs"]

    symptoms = C.dependency_symptoms(ctx)
    assert symptoms and symptoms[0]["match"] == "no rows"
    assert "orders" in symptoms[0]["text"]
    referenced = [Path(item["file"]).name for item in C.workspace_files_referenced(ctx)]
    assert referenced == ["__deployment__.py", "dq.py"]

    assert outcome(prep, "upstream_inspected_on_dependency_symptoms") == C.FALSE
    upstream = prep.results["upstream_inspected_on_dependency_symptoms"]
    assert "no other job's run" in upstream.reasoning
    assert outcome(prep, "workspace_file_read_when_referenced") == C.FALSE
    assert outcome(prep, "fix_names_target_and_change") == C.FALSE
    assert outcome(prep, "open_points_declared") == C.FALSE
    assert outcome(prep, "summary_has_required_sections") == C.FALSE
    assert outcome(prep, "evidence_has_provenance") == C.FALSE
    # the run record was quoted as `status: failed; profile: prod`, which is what it says
    assert outcome(prep, "evidence_excerpts_exist") == C.TRUE
    # the three metadata calls it did make are read as such
    assert outcome(prep, "run_record_read") == C.TRUE
    assert outcome(prep, "record_read_before_logs") == C.TRUE
    assert outcome(prep, "no_data_access") == C.TRUE


def test_a_transformation_reading_a_table_that_does_not_exist():
    """`analytics_marts` failed in extract on `Table daily_ad_metrics not found`, with the
    traceback naming `transformations/analytics.py` line 103. The inspector never opened it."""
    prep = replay("transformation_missing_table")
    ctx = prep.ctx
    assert ctx.classification == "code"

    referenced = C.workspace_files_referenced(ctx)
    assert referenced[0]["file"].endswith("transformations/analytics.py")
    assert referenced[0]["at"] == 103
    assert all(not item["file"].startswith("/usr/local/lib") for item in referenced)
    symptoms = C.dependency_symptoms(ctx)
    # the log repeats the error in the traceback and the step summary; the raising source line
    # with its `{table_name}` placeholder is left out
    assert symptoms
    assert {item["match"] for item in symptoms} == {"Table `daily_ad_metrics` not found"}

    result = prep.results["workspace_file_read_when_referenced"]
    assert result.outcome == C.FALSE
    assert "analytics.py line 103" in result.reasoning
    assert outcome(prep, "upstream_inspected_on_dependency_symptoms") == C.FALSE
    assert outcome(prep, "fix_names_target_and_change") == C.FALSE
    assert outcome(prep, "summary_has_required_sections") == C.FALSE
    # the run record quoted as `status: failed; duration_seconds: 12.36389` is found in the
    # record; the warning quoted with the inspector's own aside appended is not verbatim
    placements = {item["index"]: item["status"] for item in C.excerpt_placements(ctx)}
    assert placements[2] == C.EXCERPT_UNCITED
    assert placements[3] == C.EXCERPT_MISSING
    excerpts = prep.results["evidence_excerpts_exist"]
    assert excerpts.outcome == C.FALSE and "Warning only" in excerpts.reasoning

    windows = json.loads(prep.judge_inputs["evidence_windows"])
    assert windows["dependency_symptoms"][0]["match"] == "Table `daily_ad_metrics` not found"
    assert windows["workspace_files_referenced"][0]["at"] == 103
    assert windows["files_read"] == []
    owners = {frame["owner"] for frame in windows["traceback_frames"]}
    assert owners == {"platform", "workspace"}


def test_a_green_run_hiding_a_failed_load():
    """`jaffle_shop_dq` completed, and its log holds a BigQuery 400 and `run_checks skipped`.

    A `job.success:` trigger started this inspection, which the shipped definition does not
    resolve, so the checks that assume a failed run stand aside rather than misfire.
    """
    prep = replay("green_run_masked_failure")
    ctx = prep.ctx
    assert ctx.trigger.startswith("job.success:")
    assert str(ctx.failed_run.get("status")) == "completed"

    assert outcome(prep, "latest_failed_run_resolved") == C.NA
    assert outcome(prep, "pipeline_trace_read") == C.NA
    # the only frame the log names is `contextlib.py`, the standard library's
    assert C.workspace_files_referenced(ctx) == []
    assert outcome(prep, "workspace_file_read_when_referenced") == C.NA
    assert outcome(prep, "summary_has_required_sections") == C.FALSE
    assert outcome(prep, "fix_names_target_and_change") == C.FALSE


def test_an_inspection_that_aborted_on_a_data_tool():
    """The inspector called `list_tables`, which the sandbox cannot serve, and aborted.

    The definition grants no `data` axis, so the call itself is the finding; the abort after
    two calls that looked for a run is the second.
    """
    prep = replay("aborted_on_data_tool")
    ctx = prep.ctx
    assert ctx.status == "aborted"
    assert [call.tool for call in ctx.tool_calls][-2:] == ["list_tables", "get_row_counts"]

    result = prep.results["no_data_access"]
    assert result.outcome == C.FALSE and "list_tables" in result.reasoning
    assert outcome(prep, "aborted_without_investigation") == C.FALSE
    assert outcome(prep, "agent_profile_not_prod") == C.FALSE
    # an aborted summary is exception text, so the shape checks stand aside
    assert outcome(prep, "summary_has_required_sections") == C.NA
    assert outcome(prep, "open_points_declared") == C.NA
    assert outcome(prep, "summary_free_of_instruction_text") == C.TRUE


def test_a_data_quality_job_launched_by_a_tag_while_its_producer_was_paused():
    """`ads_platform_dq` was started by `tag:ads` and raised `SchemaNotFoundError`; the producer
    `ads_platform` is paused with no run. The inspector found the producer and told the reader
    to remove `ads` from the DQ job's tags, in one sentence with the unpause."""
    prep = replay("dq_launched_by_tag_without_producer")
    ctx = prep.ctx
    assert ctx.classification == "config"

    result = prep.results["no_orchestration_change_recommended"]
    assert result.outcome == C.JUDGE
    fields = {hit["field"] for hit in result.metadata["hits"]}
    assert fields == {"proposed_fix", "fix_change", "Recommendation"}
    assert all("tag" in hit["match"] or "expos" in hit["match"]
               for hit in result.metadata["hits"])
    windows = json.loads(prep.judge_inputs["evidence_windows"])
    assert windows["orchestration_changes"] == result.metadata["hits"]
    assert "no_orchestration_change_recommended" in windows["open_checks"]

    chained = prep.results["recommendation_one_action_per_bullet"]
    assert chained.outcome == C.FALSE and chained.metadata["verb"].lower() == "run"
    target = prep.results["fix_target_is_one_thing"]
    assert target.outcome == C.FALSE and "line 199 and" in target.reasoning
    # `SchemaNotFoundError` on the producer's pipeline is a dependency symptom, and the
    # inspector did look the producer up: its run list and its deployed definition
    symptoms = C.dependency_symptoms(ctx)
    assert symptoms and symptoms[0]["match"].lower().startswith("schema")
    assert outcome(prep, "upstream_inspected_on_dependency_symptoms") == C.TRUE
    assert outcome(prep, "job_declaration_read") == C.TRUE
    assert C.other_runs_read(ctx) == []


def test_a_cursor_value_that_only_a_comment_carries():
    """`load_jaffle_bad_incremental` failed on `IncrementalCursorPathMissing` for `updated_at`.
    The inspector read the resource, cited the `# BUG: orders have ordered_at` comment as a
    claim and put `ordered_at` in `fix_change` with an open point saying no record confirms
    it."""
    prep = replay("cursor_value_from_a_comment")
    ctx = prep.ctx
    assert ctx.classification == "config"
    assert ctx.fix_change and "ordered_at" in ctx.fix_change

    claims = [item for item in ctx.evidence if item["provenance"] == "repository_comment"]
    assert len(claims) == 1 and "# BUG" in claims[0]["excerpt"]
    assert outcome(prep, "high_confidence_rests_on_facts") == C.TRUE
    declared = prep.results["open_points_declared"]
    assert declared.outcome == C.TRUE and "repository_comment" in declared.reasoning
    assert outcome(prep, "fix_target_is_one_thing") == C.TRUE
    assert outcome(prep, "no_orchestration_change_recommended") == C.TRUE
    assert outcome(prep, "workspace_file_read_when_referenced") == C.TRUE
    # the replace and the deploy sit in one bullet, then a second sentence about confirming
    assert outcome(prep, "recommendation_one_action_per_bullet") == C.FALSE


def test_the_profile_check_reads_the_run_record():
    for name in EARLIER_DEFINITION:
        result = replay(name).results["agent_profile_not_prod"]
        assert result.outcome == C.FALSE, name
        assert 'require={"profile": "access"}' in result.reasoning
    for name in CURRENT_DEFINITION:
        result = replay(name).results["agent_profile_not_prod"]
        assert result.outcome == C.TRUE, name
        assert "access" in result.reasoning


# runs of the definition with the provenance, fix and summary rules, on the same workspace


def test_a_run_that_followed_the_lead_and_pinned_the_value_passes_every_deterministic_check():
    """`analytics_marts` failed on an unresolved named destination. The inspector read the
    deployment module at the line the traceback named, searched the workspace for the
    destination setting, read the job definition, and named the key and the value."""
    prep = replay("config_missing_destination_type")
    ctx = prep.ctx
    assert [id for id, result in prep.results.items() if result.outcome == C.FALSE] == [
        "recommendation_one_action_per_bullet", "recommendation_is_the_action"]
    assert ctx.classification == "config"
    assert ctx.fix_target and ctx.fix_change
    assert {call.tool for call in ctx.tool_calls} >= {"Read", "Grep", "dlthub_get_job"}
    assert [entry["title"] for entry in ctx.summary_sections["sections"]] == list(
        C.REQUIRED_SUMMARY_SECTIONS)
    assert {item["provenance"] for item in ctx.evidence} >= {"run_log", "workspace_file",
                                                              "job_definition", "run_record"}
    assert outcome(prep, "workspace_file_read_when_referenced") == C.TRUE
    assert outcome(prep, "job_definition_read_for_config") == C.TRUE
    assert outcome(prep, "diagnosis_quotes_evidence") == C.TRUE
    assert outcome(prep, "fix_names_target_and_change") == C.TRUE
    assert outcome(prep, "high_confidence_rests_on_facts") == C.TRUE
    assert outcome(prep, "agent_profile_not_prod") == C.TRUE
    # what the deterministic layer cannot see: the value `snowflake` came from the job's
    # display-name prose, labelled `job_definition`. `repository_prose_labelled` is the judge
    # check that caught it on the platform
    prose = [item for item in ctx.evidence if "Snowflake" in str(item.get("excerpt"))]
    assert prose and prose[0]["provenance"] == "job_definition"


def test_a_run_that_could_not_establish_the_value_leaves_it_open_and_passes():
    """`jaffle_shop_dq` failed the same way. This inspector found no artifact naming the
    backend, left `fix_change` empty, and said so under Confidence and in `open_points`."""
    prep = replay("config_missing_destination_type_value_open")
    ctx = prep.ctx
    assert [id for id, result in prep.results.items() if result.outcome == C.FALSE] == [
        "recommendation_one_action_per_bullet", "recommendation_is_the_action"]
    assert ctx.fix_target and not ctx.fix_change
    assert ctx.open_points and "destination_type" in ctx.open_points[0]
    result = prep.results["fix_names_target_and_change"]
    assert result.outcome == C.TRUE and "open_points" in result.reasoning
    assert outcome(prep, "open_points_declared") == C.TRUE
    assert outcome(prep, "confidence_carries_open_points") == C.TRUE
    reads = [call for call in ctx.file_reads if call.tool == "Read"]
    assert {C.command_of(call.detail)[:40] for call in reads} or reads
    assert any("utils/dq.py" in call.detail for call in reads)
    assert any("__deployment__.py" in call.detail for call in reads)


def test_a_missing_table_followed_to_a_producer_that_never_ran():
    """`analytics_marts` failed on `Table contact not found`. The inspector read the
    transformation and the deployment module, listed the runs of the Salesforce producer,
    found none, and classified `upstream_data` with the producer named."""
    prep = replay("dependency_followed_to_producer")
    ctx = prep.ctx
    assert ctx.classification == "upstream_data"
    assert {item["match"] for item in C.dependency_symptoms(ctx)} == {"Table `contact` not found"}
    assert C.workspace_files_referenced(ctx)[0]["file"].endswith("transformations/analytics.py")

    upstream = prep.results["upstream_inspected_on_dependency_symptoms"]
    assert upstream.outcome == C.TRUE and "dlthub_list_runs" in upstream.reasoning
    assert outcome(prep, "workspace_file_read_when_referenced") == C.TRUE
    assert outcome(prep, "only_inspected_run_logs") == C.TRUE
    assert outcome(prep, "single_run_scope") == C.TRUE
    assert outcome(prep, "fix_names_target_and_change") == C.TRUE
    assert outcome(prep, "open_points_declared") == C.TRUE
    # a line of `sources/salesforce.py` is not a position in the log, so it does not disorder
    # the log items; with one log item there is nothing to order
    assert outcome(prep, "evidence_sorted_by_line") == C.NA
    # the third open point is paraphrased under Confidence rather than repeated; the rule asks
    # for the point to be stated, not copied, and the judge's `open_points_stated` agrees
    assert outcome(prep, "confidence_carries_open_points") == C.TRUE
    # the Diagnosis quoted a log line holding backticks and escaped them with backslashes,
    # which the platform UI rendered as a broken span
    spans = prep.results["summary_code_spans_balanced"]
    assert spans.outcome == C.FALSE and "backslash" in spans.reasoning
    assert [id for id, r in prep.results.items() if r.outcome == C.FALSE] == [
        "recommendation_one_action_per_bullet", "recommendation_is_the_action",
        "summary_code_spans_balanced", "code_excerpt_free_of_prose"]
    # the producer's declaration was quoted with its docstring under `workspace_file`
    assert "docstring" in prep.results["code_excerpt_free_of_prose"].reasoning
