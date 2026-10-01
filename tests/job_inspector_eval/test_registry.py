"""The registry is the one list of check ids. The prompt and the spec must agree with it.

The agent ships its `AGENT.md` and `checks.py` and no prose beside them: a document restating
the registry drifts from it, and the checks carry their own instruction in the first paragraph
of each docstring. What an author or an operator needs is in the `create-background-agent` and
`evaluate-background-agent` skills, which the last three tests here hold to their own rules.
"""

import re
from pathlib import Path

from conftest import AGENT_DIR

import checks as C

AGENT_MD = (AGENT_DIR / "AGENT.md").read_text()

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "workbench" / "init" / "skills"
CREATE_SKILL = SKILLS_ROOT / "create-background-agent"
EVALUATE_SKILL = SKILLS_ROOT / "evaluate-background-agent"
AGENT_SKILL_FILES = sorted(
    path for skill in (CREATE_SKILL, EVALUATE_SKILL) for path in skill.glob("*.md")
)
"""Everything the two skills ship. `create-background-agent` owns what is true of any agent and
`evaluate-background-agent` only what is true of a grader, so the rules below run over both."""

_RUBRIC_ID = re.compile(r"^\*\*`([a-z_]+)`\*\*", re.M)
_PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.S)
_FENCED_BLOCK = re.compile(r"```[\w-]*\n(.*?)```", re.S)
_SKILL_REF = re.compile(r"\(`([a-z][\w-]*)`\)")


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


def test_the_agent_ships_no_prose_beside_its_definition():
    """A document restating the registry drifts from it; the docstrings carry the rules."""
    beside = {path.name for path in AGENT_DIR.glob("*.md")}
    assert beside == {"AGENT.md"}


TRANSCRIPT_ACCESSORS = ("tool_calls", "calls_matching", "shell_commands", "first_call_index",
                        "events_before_call", "runs_read", "transcript_blind", "ctx.events")
TRACE_BACKED_TRANSCRIPT_READERS = {"no_data_access", "no_write_tool_used"}
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


def test_the_shipped_definitions_declare_read_only_access():
    """What `inspector_access_read_only` grades at run time must hold in the repository.

    An empty grant passes: the evaluator has one, since everything it reads is fetched for it.
    """
    for definition in sorted(AGENT_DIR.parent.glob("*/AGENT.md")):
        access = C.parse_access(definition.read_text())
        for axis, verbs in access.items():
            allowed = C.READ_ONLY_ACCESS.get(axis)
            assert allowed is not None, f"{definition} grants the {axis} axis"
            assert set(verbs) <= allowed, f"{definition} grants {axis}: {verbs}"


def test_the_inspector_definition_sits_where_the_evaluator_looks_for_it():
    """The path the check reads is where the installer writes the definition."""
    assert C.INSPECTOR_DEFINITION_PATH == ".claude/dlthub/agents/job-inspector/AGENT.md"
    assert (AGENT_DIR.parent / "job-inspector" / "AGENT.md").is_file()


def test_every_check_has_a_category_the_summary_renders():
    for entry in C.CHECKS.values():
        assert entry.category in C.CATEGORIES, entry.id
        assert entry.category in C.CATEGORY_TITLES


def test_every_deploy_snippet_pins_the_read_only_profile():
    """An agent job without a profile runs on `prod`, which `agent_profile_not_prod` fails."""
    blocks = [
        block
        for path in AGENT_SKILL_FILES
        for block in _PYTHON_BLOCK.findall(path.read_text())
    ]
    declarations = sum(block.count("run.agent(") for block in blocks)
    assert declarations
    pinned = sum(block.count('require={"profile": "access"}') for block in blocks)
    assert pinned >= declarations


def test_no_code_block_is_copied_between_the_agent_skill_files():
    """The two skills are cut by ownership, so the same snippet belongs to one of them.

    Copied frontmatter and copied `run.agent` snippets are where that split gives way first,
    and an exact comparison is cheap. A paraphrase in prose goes uncaught, which is what the
    line each reference file opens with guards.
    """
    seen: dict[str, Path] = {}
    for path in AGENT_SKILL_FILES:
        for body in _FENCED_BLOCK.findall(path.read_text()):
            normalised = " ".join(body.split())
            if not normalised:
                continue
            assert normalised not in seen, (
                f"{path.name} repeats a code block from {seen[normalised].name}"
            )
            seen[normalised] = path


def test_every_skill_reference_in_the_agent_skills_resolves():
    """The validator reads `(`name`)` references in `rules/workflow.md` only, and `init` ships
    none, so the handover between these two skills is checked here."""
    shipped = {
        path.name
        for path in (REPO_ROOT / "workbench").glob("*/skills/*")
        if (path / "SKILL.md").is_file()
    }
    referenced = set()
    for path in AGENT_SKILL_FILES:
        referenced |= set(_SKILL_REF.findall(path.read_text()))
    assert "create-background-agent" in referenced
    assert "evaluate-background-agent" in referenced
    assert referenced <= shipped, sorted(referenced - shipped)


def _declared_output() -> dict:
    """The output schema as a model receives it, read out of the shipped `AGENT.md`."""
    import yaml

    return yaml.safe_load(AGENT_MD.split("---", 2)[1])["output"]


def test_no_declared_object_is_left_without_properties():
    """A strict validator refuses an object schema with no `properties`, so OpenAI's structured
    output falls back or rejects it. Every object the judge is shown names its fields."""
    bare = []

    def walk(node, path="output"):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" not in node:
                bare.append(path)
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(_declared_output())
    assert bare == []


def test_the_batch_fields_declare_what_checks_py_writes():
    """`window`, `evaluations` and `skipped_runs` are filled in Python, so the schema is the
    one place they can drift from the code."""
    properties = _declared_output()["properties"]
    batch = C.BatchPrep(job_ref="jobs.x.job_inspector")
    batch.skipped.append({"run_id": "r", "reason": "still running"})
    final = C.finalize_batch([{"inspector_run_id": "a", "checks": []}], batch)

    assert set(properties["window"]["properties"]) == set(final["window"])
    assert set(properties["evaluations"]["items"]["properties"]) == set(final["evaluations"][0])
    assert set(properties["skipped_runs"]["items"]["properties"]) == set(final["skipped_runs"][0])


def test_the_output_schema_stays_small():
    """The judge reads the whole schema on every run, and a large one has failed to launch."""
    import json

    assert len(json.dumps(_declared_output())) < 7_800
