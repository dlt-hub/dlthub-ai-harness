"""The evaluation a reader sees, rendered over a captured inspector run.

`finalize` turns the deterministic results and the judge's answers into the markdown the
platform UI shows. The golden file per case under `fixtures/rendered/` is that markdown,
reviewed by hand, so a diff on one is a change in what the reader reads. The judge answers
come from `fixtures/judge_answers/`, one reviewed answer and reasoning per open check, rather
than the blanket stubs the other tests use: the reasonings are what the summary quotes, and a
stub renders a summary nobody would get.

Regenerate the goldens with

    UPDATE_GOLDEN=1 uv run --group test pytest tests/job_inspector_eval/test_rendered_summary.py

and read the diff before committing it.
"""

import json
import os
from pathlib import Path

import pytest

import checks as C

from test_captured_runs import CAPTURED, replay

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ANSWERS = FIXTURES / "judge_answers"
RENDERED = FIXTURES / "rendered"
CASES = sorted(path.stem for path in ANSWERS.glob("*.json"))


def judged(case: str):
    """One case finalized the way a real evaluation finalizes it."""
    prep = replay(case)
    judge = json.loads((ANSWERS / f"{case}.json").read_text(encoding="utf-8"))
    return prep, C.finalize(judge, prep)


@pytest.fixture(scope="module")
def evaluations():
    return {case: judged(case) for case in CASES}


@pytest.mark.parametrize("case", CASES)
def test_the_answers_cover_the_open_checks_and_nothing_else(case, evaluations):
    prep, _ = evaluations[case]
    judge = json.loads((ANSWERS / f"{case}.json").read_text(encoding="utf-8"))
    assert [entry["id"] for entry in judge["checks"]] == list(C.judge_ids(prep.results))
    assert all(entry["outcome"] in (C.TRUE, C.FALSE, C.NA) for entry in judge["checks"])
    assert all(entry["reasoning"] for entry in judge["checks"])


@pytest.mark.parametrize("case", CASES)
def test_the_rendered_summary_matches_the_golden(case, evaluations):
    _, final = evaluations[case]
    golden = RENDERED / f"{case}.md"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(final["summary"], encoding="utf-8")
    assert golden.is_file(), f"no golden for {case}; regenerate with UPDATE_GOLDEN=1"
    assert final["summary"] == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("case", CASES)
def test_the_golden_survives_the_ui(case, evaluations):
    """The formatting faults the platform UI showed, over reasonings taken from a real log."""
    _, final = evaluations[case]
    summary = final["summary"]
    assert summary.startswith("## Findings\n")
    assert summary.index("## Scope") < summary.index("## Detailed evaluation results")
    assert summary.count("`") % 2 == 0
    assert "\\`" not in summary
    assert "<" not in summary.replace("<br>", "")
    rows = [line for line in summary.splitlines() if line.startswith("| `")]
    decided = [entry for entry in final["checks"] if entry["outcome"] != C.NA]
    assert len(rows) == len(decided)
    assert not [row for row in rows if "| N/A |" in row]
    for row in rows:
        assert row.count("|") == 6, row


@pytest.mark.parametrize("case", CASES)
def test_every_broken_instruction_reaches_the_reader_in_words(case, evaluations):
    _, final = evaluations[case]
    for entry in final["checks"]:
        if entry["outcome"] != C.FALSE:
            continue
        assert f"(`{entry['id']}`)" in final["summary"]
        assert C.instruction_of(entry["id"]) in final["summary"]


def test_a_data_tool_makes_the_security_finding_the_first_thing_read(evaluations):
    _, final = evaluations["aborted_on_data_tool"]
    findings = final["summary"].split("## Scope")[0]
    assert "A security rule was broken: " in findings
    assert findings.index("A security rule was broken: ") < findings.index(
        "- Instruction following: "
    )
    assert "list_tables" in findings


def test_one_evaluation_recommends_nothing(evaluations):
    for case in CASES:
        _, final = evaluations[case]
        assert final["recommendation"] == ""
        assert "## Recommendation" not in final["summary"]


def test_a_clean_run_reads_as_a_short_report(evaluations):
    """The run that broke least still reports what it broke, and no more."""
    _, final = evaluations["config_missing_destination_type"]
    false = [entry["id"] for entry in final["checks"] if entry["outcome"] == C.FALSE]
    assert set(false) == {
        "recommendation_is_the_action",
        "recommendation_one_action_per_bullet",
        "confidence_reason_stated",
        # the job label cited as a setting, reported by Python and left out of the judge's
        # `repository_prose_labelled` answer so one mistake is reported once
        "evidence_provenance_matches_source",
    }
    assert final["passed"] is False
    assert "- Quality: " in final["summary"]


def test_every_capture_with_answers_is_a_capture():
    assert CASES
    for case in CASES:
        assert (CAPTURED / case).is_dir()
