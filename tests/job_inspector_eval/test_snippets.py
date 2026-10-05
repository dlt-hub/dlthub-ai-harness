"""The deployment snippets in the docs are checked against `checks.py`.

A snippet is what a workspace copies, and the one in `advanced-patterns.md` had drifted to a
call shape `checks.py` no longer supports. Every name a snippet reads off the module has to
exist, and every call it makes has to bind against the real signature.
"""

import ast
import asyncio
import importlib
import inspect
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import checks as C

from test_captured_runs import CAPTURED
from test_captured_window import INSPECTOR_JOB as WINDOW_JOB, CASES as WINDOW_CASES, window

REPO = Path(__file__).resolve().parents[2]
DOCS = (
    REPO / "BACKGROUND_AGENTS.md",
    REPO / "workbench/dlthub-platform/skills/deploy-workspace/advanced-patterns.md",
)
_PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.S)


CHECKS_MODULE = "dlthub_agent_checks"


def blocks():
    """(document, source) per python block that loads `checks.py`."""
    for path in DOCS:
        for position, source in enumerate(_PYTHON_BLOCK.findall(path.read_text())):
            if CHECKS_MODULE in source:
                yield path.name, source


SNIPPETS = list(blocks())
IDS = [f"{name}#{position}" for position, (name, _) in enumerate(SNIPPETS)]


def read_off_checks(tree: ast.Module) -> list[str]:
    """Every `checks.<name>` the snippet reads."""
    return [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "checks"
    ]


def test_the_docs_carry_the_snippets():
    assert len(SNIPPETS) == 4  # one per deployment, in each document


@pytest.mark.parametrize("name,source", SNIPPETS, ids=IDS)
def test_every_name_a_snippet_reads_exists(name, source):
    tree = ast.parse(source)

    missing = [symbol for symbol in read_off_checks(tree) if not hasattr(C, symbol)]

    assert missing == [], f"{name} reads {missing} off checks.py"


@pytest.mark.parametrize("name,source", SNIPPETS, ids=IDS)
def test_every_call_binds_against_the_real_signature(name, source):
    """Positional and keyword arguments only; a `*args` in a snippet would be a different
    test. The values are placeholders, so this checks the shape, not the types."""
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "checks":
            continue
        target = getattr(C, node.func.attr, None)
        if not callable(target):
            continue
        signature = inspect.signature(target)
        signature.bind(
            *[object() for _ in node.args],
            **{keyword.arg: object() for keyword in node.keywords if keyword.arg},
        )


# running the snippets, not just parsing them


LINKS_LOADER = '''import importlib.util
_spec = importlib.util.spec_from_file_location(
    "dlthub_agent_links", ".claude/dlthub/agents/job-inspector/links.py")
links = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(links)

'''


def snippet(title: str) -> str:
    """The python block under a heading of `advanced-patterns.md`, with `links` loaded.

    The document loads `links` in its first snippet and the later ones use it, so a block
    taken out of the document needs that loader in front of it.
    """
    text = (REPO / "workbench/dlthub-platform/skills/deploy-workspace"
            / "advanced-patterns.md").read_text()
    section = re.split(rf"#+ {re.escape(title)}\n", text, maxsplit=1)[1]
    return LINKS_LOADER + _PYTHON_BLOCK.search(section).group(1)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A workspace in the layout an install produces: the agent folders under `.claude`."""
    agents = tmp_path / ".claude" / "dlthub" / "agents"
    agents.mkdir(parents=True)
    source = REPO / "workbench" / "dlthub-platform" / "dlthub" / "agents"
    for name in ("job-inspector", "job-inspector-eval"):
        shutil.copytree(source / name, agents / name,
                        ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / ".dlt").mkdir()
    (tmp_path / ".dlt" / "config.toml").write_text("[runtime]\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


def load(workspace, title: str, module_name: str):
    """The snippet as an imported deployment module, its `run.agent` declarations resolved.

    A plain import, because `run.agent` reads the calling module off the stack to stamp the
    job section, and a module executed from a spec carries no frame it can read.
    """
    (workspace / f"{module_name}.py").write_text(snippet(title))
    importlib.invalidate_caches()
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


class _Loop:
    """Answers every open check TRUE, and the recommendation pass with one bullet.

    `completed`, `trace` and `base_trace` are what the launcher reads off a loop when it writes
    the job result, so a test can hand this to dlt. `completed` is false here because the stub
    answers without a turn, which sends the launcher to `base_trace`.
    """

    LOOP_TYPE = "stub"
    completed = False

    def __init__(self) -> None:
        self.runs = 0
        self.trace = {"loop_type": self.LOOP_TYPE, "turn_count": 0, "total_tokens": 0}

    def base_trace(self, inputs):
        return {"loop_type": self.LOOP_TYPE, "turn_count": 0, "inputs": inputs}

    async def run(self, inputs):
        self.runs += 1
        if inputs.get("task") == C.WRITE_THE_RECOMMENDATION:
            return {
                "status": "succeeded", "summary": "one window", "checks": [],
                "recommendation": "- In `.claude/dlthub/agents/job-inspector/AGENT.md`,"
                                  " under `## Investigate`, state the ordering rule.",
            }
        open_checks = json.loads(inputs["evidence_windows"])["open_checks"]
        return {
            "status": "succeeded", "summary": "graded", "recommendation": "",
            "checks": [{"id": id, "kind": "judge", "outcome": "TRUE", "reasoning": "fine"}
                       for id in open_checks],
        }


def test_the_window_snippet_runs_as_a_deployment_module(workspace, monkeypatch):
    """The declarations resolve against the installed agent folders and the function grades a
    window of captured runs."""
    module = load(workspace, "One report over a window", "deployment_window")
    root = captured_window(workspace)
    # the snippet loads the workspace copy of `checks.py` by path, so the fetcher it calls is
    # the one on that module, not the one this test imported
    fetch = module.checks
    monkeypatch.setattr(fetch.SdkFetcher, "connect",
                        staticmethod(lambda: fetch.FileFetcher(str(root))))
    loop = _Loop()

    report = asyncio.run(module.job_inspector_eval.__wrapped__(
        run_context={"run_id": "local", "trigger": "schedule:0 7 * * 1", "ai_loop": loop},
        inspector_job_ref=WINDOW_JOB,
        window_days=_days_back(),
    ))

    assert loop.runs == len(WINDOW_CASES) + 1  # one per run graded, then the recommendation
    assert report["status"] == "succeeded"
    assert report["window"]["runs_found"] == len(WINDOW_CASES)
    assert report["window"]["runs_evaluated"] == len(WINDOW_CASES)
    assert report["recommendation"].startswith("- In `.claude/dlthub/agents/job-inspector/")
    assert [line for line in report["summary"].splitlines() if line.startswith("## ")] == [
        "## Findings", "## Recommendation", "## Scope", "## Detailed evaluation results"
    ]


def test_the_run_snippet_delivers_the_four_entities_to_the_platform(workspace, monkeypatch):
    """Why the trimmed schema still declares four computed fields. `deliver_job_result` fills
    `object` from the declared `output`, which `resolve_agent_spec` takes off the `AGENT.md`,
    and the platform files the run under each entity. On a trigger no input carries them: the
    run id was resolved from `prev_run_id`, so the output is the only source."""
    import os

    from dlt._workspace.deployment.job_result import set_job_inputs
    from dlt._workspace.deployment.launchers.agent import _set_result_from_agent_output
    from dlt._workspace.deployment.launchers.job import deliver_job_result

    module = load(workspace, "One grade per inspector run", "deployment_run")
    root = CAPTURED / "dq_missing_input"
    run_id = sorted((root / "results").glob("*.json"))[0].stem
    fetch = module.checks
    monkeypatch.setattr(fetch.SdkFetcher, "connect",
                        staticmethod(lambda: fetch.FileFetcher(str(root))))
    loop = _Loop()

    output = asyncio.run(module.job_inspector_eval.__wrapped__(
        run_context={"run_id": "local", "trigger": "job.fail:jobs.x.job_inspector",
                     "ai_loop": loop},
        inspector_run_id=run_id,
    ))
    assert output["status"] == "succeeded"
    assert output["inspector_run_id"] == run_id

    job = module.job_inspector_eval
    job.resolve_agent_spec(os.getcwd())  # what `build_agent_loop` does on a real run
    set_job_inputs({})                   # a trigger supplies none
    _set_result_from_agent_output(job, output, loop)
    delivered = deliver_job_result(job, send=False)

    assert [entity["id"] for entity in delivered["object"]] == [
        f"job-runs/{run_id}",
        f"job/{output['inspector_job_ref']}",
        f"job/{output['failed_job_ref']}",
        f"job-runs/{output['failed_run_id']}",
    ]


def test_without_the_declared_ids_the_run_is_filed_under_nothing(workspace):
    """The counterfactual for the test above: drop the four and `hub_objects` returns []."""
    import yaml
    from dlt._workspace.deployment.entity import hub_objects

    declaration = yaml.safe_load(
        (workspace / ".claude/dlthub/agents/job-inspector-eval/AGENT.md").read_text()
        .split("---", 2)[1]
    )
    result = {"status": "succeeded", "inspector_run_id": "r1", "inspector_job_ref": "j1",
              "failed_run_id": "r2", "failed_job_ref": "j2"}
    without = {"type": "object", "properties": {
        name: spec for name, spec in declaration["output"]["properties"].items()
        if "entity_type" not in spec
    }}

    assert len(hub_objects(declaration["inputs"], {}, declaration["output"], result, "x")) == 4
    assert hub_objects(declaration["inputs"], {}, without, result, "x") == []


MANIFEST_JOBS = {
    # the first snippet pins no `section`, so its job ref takes the module name
    "Background agents": ["jobs.deployment_manifest.job_inspector"],
    "One report over a window": ["jobs.__deployment__.job_inspector",
                                 "jobs.deployment_manifest.job_inspector_eval"],
    "One grade per inspector run": ["jobs.__deployment__.job_inspector",
                                    "jobs.deployment_manifest.job_inspector_eval"],
}


@pytest.mark.parametrize("title", list(MANIFEST_JOBS))
def test_a_snippet_deploys_the_jobs_it_declares_and_nothing_else(workspace, title):
    """Manifest generation is where a wrong `entity_type` or a stray module-level name lands,
    and one bad job takes the whole manifest down with it.

    `generate_manifest` scans module-level names, so a module loaded by path deploys as a job
    of its own unless `__all__` names the jobs.
    """
    from dlt._workspace.deployment.manifest import generate_manifest, validate_manifest

    module = load(workspace, title, "deployment_manifest")
    manifest, warnings = generate_manifest(module)
    result = validate_manifest(manifest)

    assert [job["job_ref"] for job in manifest["jobs"]] == MANIFEST_JOBS[title]
    assert result.is_valid, result.errors
    assert [warning for warning in warnings if "__all__" in warning] == []


def captured_window(root: Path) -> Path:
    """The captures `test_captured_window` composes, under a root of this test's own."""
    composed = root / "window"
    composed.mkdir()
    window(composed, *WINDOW_CASES)
    return composed


def _days_back() -> int:
    """Window long enough to reach the captured runs, which carry their recorded dates."""
    oldest = datetime(2026, 9, 20, tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - oldest).days + 1
