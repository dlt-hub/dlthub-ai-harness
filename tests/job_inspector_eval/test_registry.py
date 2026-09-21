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


def test_agent_md_holds_a_rubric_for_every_check_the_judge_answers():
    rubrics = _RUBRIC_ID.findall(AGENT_MD)
    judged = [
        entry.id for entry in C.CHECKS.values() if entry.kind in (C.JUDGE, C.HYBRID)
    ]
    assert sorted(rubrics) == sorted(judged)


def test_agent_md_spells_out_no_deterministic_check():
    """The model copies the deterministic results; their rubric lives in `checks.py`."""
    deterministic = {entry.id for entry in C.CHECKS.values() if entry.kind == C.DETERMINISTIC}
    assert deterministic.isdisjoint(_RUBRIC_ID.findall(AGENT_MD))


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


def test_every_check_that_reads_the_transcript_declares_it():
    """The flag holds back a check when the parser went blind, so it must match the code."""
    import inspect

    for entry in C.CHECKS.values():
        if entry.fn is None:
            continue
        source = inspect.getsource(entry.fn)
        reads = any(accessor in source for accessor in TRANSCRIPT_ACCESSORS)
        assert entry.reads_transcript is reads, entry.id
