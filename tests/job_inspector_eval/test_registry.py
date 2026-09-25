"""The registry is the one list of check ids. The docs and the prompt must agree with it."""

import re

from conftest import AGENT_DIR

import checks as C

AGENT_MD = (AGENT_DIR / "AGENT.md").read_text()
README = (AGENT_DIR / "README.md").read_text()

_TABLE_ID = re.compile(r"^\| `([a-z_]+)` \|", re.M)
_RUBRIC_ID = re.compile(r"^\*\*`([a-z_]+)`\*\*", re.M)


def test_readme_tables_list_every_check_once():
    listed = _TABLE_ID.findall(README)
    assert sorted(listed) == sorted(C.CHECKS)
    assert len(listed) == len(set(listed))


def test_a_rubric_is_registered_for_every_check_the_judge_answers():
    judged = {entry.id for entry in C.CHECKS.values() if entry.kind in (C.JUDGE, C.HYBRID)}
    assert set(C.RUBRICS) == judged


def test_no_deterministic_check_carries_a_rubric():
    """The model copies the deterministic results; their rubric is the docstring in `checks.py`."""
    deterministic = {entry.id for entry in C.CHECKS.values() if entry.kind == C.DETERMINISTIC}
    assert deterministic.isdisjoint(C.RUBRICS)


def test_the_prompt_asks_for_the_rubrics_instead_of_spelling_them_out():
    """The Checks section is `{{ rubrics }}`: the prompt carries the applicable ones only."""
    assert "{{ rubrics }}" in AGENT_MD
    assert _RUBRIC_ID.findall(AGENT_MD) == []


def test_rubric_block_renders_only_the_ids_asked_for_in_registry_order():
    block = C.rubric_block(["summary_says_why", "no_premature_cause"])
    assert block.index("**`no_premature_cause`**") < block.index("**`summary_says_why`**")
    assert "**`summary_says_what_failed`**" not in block
    for id in ("no_premature_cause", "summary_says_why"):
        assert C.RUBRICS[id].strip() in block


def test_rubric_block_rejects_an_id_with_no_rubric():
    import pytest

    with pytest.raises(KeyError):
        C.rubric_block(["evidence_has_provenance"])


def test_no_rubric_carries_an_unrendered_placeholder():
    """dlt renders the body once; a `{{ }}` inside an injected value reaches the model raw."""
    for id, text in C.RUBRICS.items():
        assert "{{" not in text, id


def test_every_deterministic_check_documents_its_three_outcomes():
    for entry in C.CHECKS.values():
        if entry.fn is None:
            continue
        assert entry.doc, f"{entry.id} has no docstring"
        for outcome in ("TRUE", "FALSE", "N/A"):
            assert outcome in entry.doc, f"{entry.id} does not document {outcome}"


def test_the_counts_the_readme_states_are_the_counts_in_the_registry():
    kinds = [entry.kind for entry in C.CHECKS.values()]
    stated = (
        f"{len(kinds)} checks: {kinds.count(C.DETERMINISTIC)} deterministic,"
        f" {kinds.count(C.HYBRID)} hybrid, {kinds.count(C.JUDGE)} judge."
    )
    assert stated in README


def test_readme_documents_every_input_the_agent_declares():
    for name in ("inspector_run_id", "inspector_job_ref", "max_runs_read"):
        assert name in README


TRANSCRIPT_ACCESSORS = ("tool_calls", "calls_matching", "shell_commands", "first_call_index",
                        "events_before_call", "runs_read", "transcript_blind", "ctx.events")
TRACE_BACKED_TRANSCRIPT_READERS = {"no_data_access"}
"""Checks that read transcript calls but can still decide from the run trace if parsing fails."""


def test_every_check_that_reads_the_transcript_declares_it():
    """The flag holds back a check when the parser went blind, so it must match the code."""
    import inspect

    for entry in C.CHECKS.values():
        if entry.fn is None:
            continue
        source = inspect.getsource(entry.fn)
        reads = any(accessor in source for accessor in TRANSCRIPT_ACCESSORS)
        expected = reads and entry.id not in TRACE_BACKED_TRANSCRIPT_READERS
        assert entry.reads_transcript is expected, entry.id


def test_data_tool_table_matches_dlt_access_annotations():
    """A new destination tool in dlt must fail `no_data_access`, not pass silently."""
    from dlt._workspace.access import granted_verbs, required_access
    from dlt._workspace.mcp.tools import data_tools

    data_read_tools = {
        tool.__name__
        for tool in data_tools.__tools__
        if "read" in granted_verbs(required_access(tool), "data")
    }
    assert set(C.DATA_TOOLS) == data_read_tools
