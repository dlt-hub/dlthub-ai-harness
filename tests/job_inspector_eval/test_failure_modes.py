"""The failure modes of an inspector run, as fixtures.

Each case pairs a shallow inspector run with the run the definition asks for, over the same
failed log, and asserts which checks separate them: a traceback left unopened, a fix that
names no value, a missing table not followed to its producer, a gap left undeclared, a cause
copied from a comment, and a summary that leaks its own instructions.
"""

from conftest import (
    FAILED_RUN_ID,
    OLDER_RUN_ID,
    PROGRAM_START,
    context,
    failed_run,
    inspector_log,
    output,
    with_setup,
)

import checks as C

RECORD_CALL = f'  dlthub_get_run (dlthub)  {{"run_id": "{FAILED_RUN_ID}"}}'
LOG_CALL = f'  dlthub_get_run_logs (dlthub)  {{"run_id": "{FAILED_RUN_ID}"}}'


def outcomes(**overrides):
    results, errors = C.run_deterministic(context(**overrides))
    assert errors == []
    return {id: result.outcome for id, result in results.items()}


def false_ids(**overrides):
    return sorted(id for id, outcome in outcomes(**overrides).items() if outcome == C.FALSE)


def line(program_index):
    return PROGRAM_START + program_index


# case 1: a traceback that names a workspace file, and a fix that names no value
# a run on `load_jaffle_bad_incremental`

INCREMENTAL_JOB = "jobs.jaffle_shop.load_jaffle_bad_incremental"
INCREMENTAL_ERROR = (
    "dlt.extract.incremental.exceptions.IncrementalCursorPathMissing: Cursor element with JSON"
    " path 'order_date' was not found in extracted data item."
)
INCREMENTAL_LOG = [
    "2026-09-22 14:01:00 INFO  starting pipeline jaffle_bad_incremental",
    "2026-09-22 14:01:01 INFO  extract started",
    "2026-09-22 14:01:03 ERROR  step extract failed",
    "Traceback (most recent call last):",
    '  File "/workspace/jaffle_shop/bad_incremental.py", line 67, in load_orders',
    "    pipeline.run(orders_bad_incremental())",
    '  File "/usr/local/lib/python3.12/site-packages/dlt/extract/incremental/__init__.py",'
    ' line 412, in __call__',
    "    raise IncrementalCursorPathMissing(self.resource_name, self.cursor_path, item)",
    INCREMENTAL_ERROR,
    "2026-09-22 14:01:04 INFO  job finished with status failed",
]
INCREMENTAL_LINE = line(8)
FILE_READ = '  Read  {"file_path": "/workspace/jaffle_shop/bad_incremental.py"}'


def incremental_transcript(read_file):
    events = [
        "  thinks  Run record first, then the log.",
        RECORD_CALL, "     → failed",
        LOG_CALL, "     → 10 lines",
    ]
    if read_file:
        events += [
            "  thinks  The traceback names jaffle_shop/bad_incremental.py line 67; reading it.",
            FILE_READ, "     → 80 lines",
        ]
    return inspector_log(events=events)


def incremental_from_the_log_alone():
    """Every turn on metadata tools while Read, Glob and Grep were live; the fix names no
    field."""
    return output(
        classification="code", confidence="high",
        summary=(
            "The job failed with IncrementalCursorPathMissing in extract. Update"
            " `orders_bad_incremental` so its incremental cursor path matches the exact field"
            " present in the source records."
        ),
        evidence=[{"source": f"`dlthub job runs logs {FAILED_RUN_ID}` line {INCREMENTAL_LINE}",
                   "excerpt": INCREMENTAL_ERROR}],
        proposed_fix="Update `orders_bad_incremental` so its incremental cursor path matches"
                     " the exact field present in the source records",
        fix_target="", fix_change="", open_points=[],
    )


def incremental_as_required():
    return output(
        classification="code", confidence="high",
        summary=(
            "## Diagnosis\n"
            "- `load_jaffle_bad_incremental` failed in extract: the incremental cursor names a"
            " field the records do not carry.\n"
            f"- Run log line {INCREMENTAL_LINE}: `IncrementalCursorPathMissing: Cursor element"
            " with JSON path 'order_date' was not found in extracted data item`.\n"
            "- `jaffle_shop/bad_incremental.py` line 31 declares `cursor_path=\"order_date\"`;"
            " the records built at line 24 carry `ordered_at`.\n\n"
            "## Recommendation\n"
            "- In `jaffle_shop/bad_incremental.py` line 31, set `cursor_path=\"ordered_at\"`.\n"
            "- Re-run `jobs.jaffle_shop.load_jaffle_bad_incremental`.\n\n"
            "## Confidence\n"
            "- The field name comes from the resource code; the first record of the `orders`"
            " endpoint was not fetched to confirm it.\n"
            "- Confidence is high: the earliest error names the cursor path and the code"
            " declares it.\n"
        ),
        evidence=[
            {"source": f"`dlthub job runs logs {FAILED_RUN_ID}` line {INCREMENTAL_LINE}",
             "excerpt": INCREMENTAL_ERROR, "provenance": "run_log"},
            {"source": "jaffle_shop/bad_incremental.py line 31",
             "excerpt": 'cursor_path="order_date",', "provenance": "workspace_file"},
        ],
        proposed_fix="In `jaffle_shop/bad_incremental.py` line 31, set"
                     " `cursor_path=\"ordered_at\"` and re-run the job.",
        fix_target="jaffle_shop/bad_incremental.py line 31",
        fix_change='cursor_path="ordered_at"',
        open_points=["The field name comes from the resource code; the first record of the"
                     " `orders` endpoint was not fetched to confirm it."],
    )


def incremental_case(read_file, result):
    return dict(
        failed_log=with_setup(INCREMENTAL_LOG),
        failed_run=failed_run(job_ref=INCREMENTAL_JOB),
        inspector_log=incremental_transcript(read_file),
        output=result,
    )


def test_a_traceback_into_a_workspace_file_is_followed_and_the_fix_names_the_value():
    assert false_ids(**incremental_case(True, incremental_as_required())) == []
    good = outcomes(**incremental_case(True, incremental_as_required()))
    assert good["workspace_file_read_when_referenced"] == C.TRUE
    assert good["fix_names_target_and_change"] == C.TRUE
    assert good["diagnosis_quotes_evidence"] == C.TRUE
    assert good["high_confidence_rests_on_facts"] == C.TRUE
    assert good["confidence_carries_open_points"] == C.TRUE


def test_a_run_from_the_log_alone_fails_on_the_file_the_fix_and_the_shape():
    bad = outcomes(**incremental_case(False, incremental_from_the_log_alone()))
    assert bad["workspace_file_read_when_referenced"] == C.FALSE
    assert bad["fix_names_target_and_change"] == C.FALSE
    assert bad["open_points_declared"] == C.FALSE
    assert bad["evidence_has_provenance"] == C.FALSE
    assert bad["summary_has_required_sections"] == C.FALSE
    # the log line it did cite is real, so the excerpt checks stand
    assert bad["evidence_excerpts_exist"] == C.TRUE


def test_reading_the_file_alone_does_not_clear_a_fix_that_names_no_value():
    read_but_vague = outcomes(**incremental_case(True, incremental_from_the_log_alone()))
    assert read_but_vague["workspace_file_read_when_referenced"] == C.TRUE
    assert read_but_vague["fix_names_target_and_change"] == C.FALSE


def test_a_merge_key_guessed_for_a_table_without_it_is_a_hedge():
    """`products` has `sku, name, type, price, description`; the fix proposed `id`."""
    guessed = incremental_as_required()
    guessed["fix_target"] = "jaffle_shop/bad_merge.py line 20"
    guessed["fix_change"] = "merge_key set to the row identifier, typically an `id` field"
    result = C.CHECKS["fix_names_target_and_change"].fn(
        context(**incremental_case(True, guessed)))
    assert result.outcome == C.FALSE
    assert "typically" in result.reasoning


# case 2: a downstream quality job fails because the producer loaded nothing
# `quality_checks` after `load_jaffle_bad_selector`

QUALITY_JOB = "jobs.jaffle_shop.quality_checks"
LOADER_JOB = "jobs.jaffle_shop.load_jaffle_bad_selector"
UPSTREAM_RUN_ID = "66666666-6666-4666-8666-666666666666"
MISSING_TABLE = ("check orders_not_empty failed: Catalog Error: Table with name orders does"
                 " not exist!")
QUALITY_LOG = [
    "2026-09-22 15:00:00 INFO  running data quality checks on dataset jaffle_shop",
    f"2026-09-22 15:00:01 ERROR  {MISSING_TABLE}",
    "Traceback (most recent call last):",
    '  File "/workspace/jaffle_shop/quality.py", line 22, in run_checks',
    "    dataset.orders.df()",
    "duckdb.duckdb.CatalogException: Catalog Error: Table with name orders does not exist!",
    "2026-09-22 15:00:02 INFO  job finished with status failed",
]
MISSING_TABLE_LINE = line(1)


def quality_transcript(follow):
    events = [RECORD_CALL, "     → failed", LOG_CALL, "     → 7 lines"]
    if follow:
        events += [
            '  Read  {"file_path": "/workspace/jaffle_shop/quality.py"}',
            "     → 40 lines",
            "  thinks  The table is missing: the producer did not deliver. Which job loads it?",
            f'  dlthub_get_job (dlthub)  {{"job_ref": "{QUALITY_JOB}"}}',
            f"     → depends on {LOADER_JOB}",
            f'  dlthub_list_runs (dlthub)  {{"job_ref": "{LOADER_JOB}"}}',
            "     → 1 run, succeeded",
            f'  dlthub_get_run (dlthub)  {{"run_id": "{UPSTREAM_RUN_ID}"}}',
            "     → succeeded",
            f'  dlthub_get_run_logs (dlthub)  {{"run_id": "{UPSTREAM_RUN_ID}"}}',
            "     → 40 lines",
        ]
    else:
        events += [
            f'  dlthub_list_runs (dlthub)  {{"job_ref": "{QUALITY_JOB}"}}',
            "     → 2 runs",
        ]
    return inspector_log(events=events)


def quality_stopping_at_the_symptom():
    """Three metadata tools in the whole run and "there is no table in the database"."""
    return output(
        classification="upstream_data", confidence="medium",
        summary="The quality checks failed because there is no `orders` table in the"
                " database. Load the table and re-run the checks.",
        evidence=[{"source": f"`dlthub job runs logs {FAILED_RUN_ID}` line"
                             f" {MISSING_TABLE_LINE}",
                   "excerpt": MISSING_TABLE, "provenance": "run_log"}],
        proposed_fix="Load the `orders` table and re-run the quality checks.",
        fix_target="", fix_change="", open_points=[],
    )


def quality_as_required():
    return output(
        classification="upstream_data", confidence="high",
        summary=(
            "## Diagnosis\n"
            "- `quality_checks` failed because its input is missing: the producing job"
            " `load_jaffle_bad_selector` completed with 0 rows for `orders`.\n"
            f"- Run log line {MISSING_TABLE_LINE}: `Table with name orders does not exist!`.\n"
            f"- Producer run {UPSTREAM_RUN_ID} log line 14: `Load package 1 loaded 0 rows into"
            " orders`; the run itself succeeded.\n\n"
            "## Recommendation\n"
            "- Correct the `orders` selector in `jaffle_shop/bad_selector.py` so the resource"
            " yields rows, re-run `jobs.jaffle_shop.load_jaffle_bad_selector`, then the"
            " checks.\n"
            "- Leave the quality job unchanged.\n\n"
            "## Confidence\n"
            "- The selector value in `jaffle_shop/bad_selector.py` was not read, so the"
            " corrected value is open; the producer log shows 0 rows for `orders`.\n"
            "- Confidence is high: the missing table and the zero-row load name the same"
            " table.\n"
        ),
        evidence=[
            {"source": f"`dlthub job runs logs {FAILED_RUN_ID}` line {MISSING_TABLE_LINE}",
             "excerpt": MISSING_TABLE, "provenance": "run_log"},
            {"source": f"`dlthub job runs logs {UPSTREAM_RUN_ID}` line 14",
             "excerpt": "Load package 1 loaded 0 rows into orders", "provenance": "run_log"},
        ],
        proposed_fix="Correct the `orders` selector in `jaffle_shop/bad_selector.py` so the"
                     " resource yields rows, then re-run `load_jaffle_bad_selector` and the"
                     " quality checks.",
        fix_target=LOADER_JOB, fix_change="",
        open_points=["The selector value in `jaffle_shop/bad_selector.py` was not read, so the"
                     " corrected value is open; the producer log shows 0 rows for `orders`."],
    )


def quality_case(follow, result):
    return dict(
        failed_log=with_setup(QUALITY_LOG),
        failed_run=failed_run(job_ref=QUALITY_JOB),
        neighbours=[failed_run(job_ref=QUALITY_JOB),
                    {"id": OLDER_RUN_ID, "number": 11, "status": "succeeded"}],
        inspector_log=quality_transcript(follow),
        output=result,
    )


def test_a_missing_table_is_followed_to_the_producing_job():
    good = outcomes(**quality_case(True, quality_as_required()))
    assert good["upstream_inspected_on_dependency_symptoms"] == C.TRUE
    assert good["only_inspected_run_logs"] == C.TRUE  # the one producer log is allowed
    assert good["single_run_scope"] == C.TRUE
    assert good["evidence_excerpts_exist"] == C.TRUE  # the producer's log is not held
    assert good["fix_names_target_and_change"] == C.TRUE  # the open value is declared
    assert false_ids(**quality_case(True, quality_as_required())) == []


def test_a_run_that_stops_at_the_missing_table_is_caught():
    bad = outcomes(**quality_case(False, quality_stopping_at_the_symptom()))
    assert bad["upstream_inspected_on_dependency_symptoms"] == C.FALSE
    assert bad["fix_names_target_and_change"] == C.FALSE
    assert bad["open_points_declared"] == C.FALSE
    assert bad["summary_has_required_sections"] == C.FALSE
    reason = C.CHECKS["upstream_inspected_on_dependency_symptoms"].fn(
        context(**quality_case(False, quality_stopping_at_the_symptom()))).reasoning
    assert "does not exist" in reason and "no other job's run" in reason


# case 3: the evidence is insufficient and the run says so, or does not

TOOL_ERROR = "Error calling tool 'Read': ENOENT jaffle_shop/bad_incremental.py"


def truncated_transcript():
    return inspector_log(events=[RECORD_CALL, "     → failed", LOG_CALL, "     → 10 lines",
                                 FILE_READ, TOOL_ERROR])


def test_a_run_whose_file_read_failed_must_declare_the_gap():
    silent = incremental_as_required()
    silent["confidence"] = "medium"
    silent["open_points"] = []
    silent["fix_change"] = ""
    bad = outcomes(failed_log=with_setup(INCREMENTAL_LOG), inspector_log=truncated_transcript(),
                   output=silent)
    assert bad["open_points_declared"] == C.FALSE
    assert bad["fix_names_target_and_change"] == C.FALSE

    honest = incremental_as_required()
    honest["confidence"] = "medium"
    honest["fix_change"] = ""
    honest["open_points"] = [
        "`jaffle_shop/bad_incremental.py` could not be read (ENOENT), so the field the cursor"
        " should name is open; check the resource's `cursor_path` against the first record.",
    ]
    honest["summary"] = honest["summary"].replace(
        "- The field name comes from the resource code; the first record of the `orders`"
        " endpoint was not fetched to confirm it.",
        "- `jaffle_shop/bad_incremental.py` could not be read (ENOENT), so the field the"
        " cursor should name is open; check the resource's `cursor_path` against the first"
        " record.",
    )
    honest["evidence"] = honest["evidence"][:1]
    good = outcomes(failed_log=with_setup(INCREMENTAL_LOG), inspector_log=truncated_transcript(),
                    output=honest)
    assert good["open_points_declared"] == C.TRUE
    assert good["confidence_carries_open_points"] == C.TRUE
    assert good["fix_names_target_and_change"] == C.TRUE


# case 4: a cause copied from a docstring
# prose stating the answer, cited as evidence

DOCSTRING = "# NOTE: the source records carry ordered_at, not order_date"


def test_high_confidence_on_a_docstring_alone_fails_and_a_code_line_next_to_it_passes():
    prose_only = incremental_as_required()
    prose_only["evidence"] = [
        {"source": "jaffle_shop/bad_incremental.py line 13", "excerpt": DOCSTRING,
         "provenance": "repository_comment"},
    ]
    result = C.CHECKS["high_confidence_rests_on_facts"].fn(
        context(**incremental_case(True, prose_only)))
    assert result.outcome == C.FALSE
    assert "repository_comment" in result.reasoning

    corroborated = incremental_as_required()
    corroborated["evidence"].append(
        {"source": "jaffle_shop/bad_incremental.py line 13", "excerpt": DOCSTRING,
         "provenance": "repository_comment"})
    good = outcomes(**incremental_case(True, corroborated))
    assert good["high_confidence_rests_on_facts"] == C.TRUE
    # a claim among the evidence forces an open point, which this output declares
    assert good["open_points_declared"] == C.TRUE


def test_a_docstring_labelled_as_code_is_caught_by_the_source_check_only_when_the_source_is_a_log():
    """A comment in a `.py` file fits `workspace_file` by source; the judge's
    `repository_prose_labelled` is what tells code from prose."""
    labelled_code = incremental_as_required()
    labelled_code["evidence"].append(
        {"source": "jaffle_shop/bad_incremental.py line 13", "excerpt": DOCSTRING,
         "provenance": "workspace_file"})
    assert outcomes(**incremental_case(True, labelled_code))[
        "evidence_provenance_matches_source"] == C.TRUE

    log_as_code = incremental_as_required()
    log_as_code["evidence"][0]["provenance"] = "workspace_file"
    assert outcomes(**incremental_case(True, log_as_code))[
        "evidence_provenance_matches_source"] == C.FALSE


# case 5: the summary structure, and the instruction text that must not leak into it


def test_instruction_questions_next_to_the_headings_fail_two_checks():
    leaked = incremental_as_required()
    questions = {
        "## Diagnosis": "## Diagnosis [What was the root cause of the issue?]",
        "## Recommendation":
            "## Recommendation [Which prompt should the user give to their coding agent?]",
        "## Confidence":
            "## Confidence [What are limitations of this diagnosis and recommendation?]",
    }
    for heading, with_question in questions.items():
        leaked["summary"] = leaked["summary"].replace(heading, with_question)
    bad = outcomes(**incremental_case(True, leaked))
    assert bad["summary_has_required_sections"] == C.FALSE
    assert bad["summary_free_of_instruction_text"] == C.FALSE
