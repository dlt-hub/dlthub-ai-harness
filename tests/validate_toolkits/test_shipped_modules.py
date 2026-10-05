"""A module in an agent folder installs with it, and the definition has to name it.

dlt's agent spec has no field for code, so nothing in the `AGENT.md` calls `checks.py` or
`links.py`. The deployment function imports them. That leaves the definition as the one
installed file that can tell a reader the module is there.
"""

from pathlib import Path

from fakes import REPO_ROOT

import validate_toolkits as V


def module_errors(tmp_path: Path, manifest: str, modules: dict[str, str]) -> list[str]:
    agent_dir = tmp_path / "an-agent"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text(manifest)
    for name, source in modules.items():
        (agent_dir / name).write_text(source)
    errors: list[str] = []
    V._validate_shipped_modules(
        "tk", "agents/an-agent/AGENT.md", agent_dir, agent_dir / "AGENT.md", errors, []
    )
    return errors


def test_an_agent_with_no_module_passes(tmp_path: Path) -> None:
    assert module_errors(tmp_path, "# an agent\n", {}) == []


def test_a_named_module_passes(tmp_path: Path) -> None:
    manifest = "# `checks.py` runs around the loop\n"

    assert module_errors(tmp_path, manifest, {"checks.py": "x = 1\n"}) == []


def test_an_unnamed_module_fails(tmp_path: Path) -> None:
    errors = module_errors(tmp_path, "# an agent\n", {"checks.py": "x = 1\n"})

    assert len(errors) == 1
    assert "checks.py" in errors[0]


def test_every_unnamed_module_is_listed(tmp_path: Path) -> None:
    errors = module_errors(
        tmp_path, "# `links.py`\n", {"links.py": "x = 1\n", "checks.py": "y = 2\n"}
    )

    assert len(errors) == 1
    assert "checks.py" in errors[0] and "links.py" not in errors[0]


def test_the_shipped_agents_name_the_modules_beside_them() -> None:
    agents = Path(REPO_ROOT) / V.AI_DIR / "dlthub-platform" / "dlthub" / "agents"
    errors: list[str] = []
    for agent_dir in sorted(p for p in agents.iterdir() if p.is_dir()):
        V._validate_shipped_modules(
            "dlthub-platform", agent_dir.name, agent_dir, agent_dir / "AGENT.md", errors, []
        )

    assert errors == []


def test_a_stray_file_in_the_folder_fails(tmp_path: Path) -> None:
    """`shutil.copytree` filters nothing, so bytecode left by a test run installs too."""
    agent_dir = tmp_path / "an-agent"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text("# `checks.py`\n")
    (agent_dir / "checks.py").write_text("x = 1\n")
    (agent_dir / "__pycache__").mkdir()
    errors: list[str] = []

    V._validate_shipped_modules(
        "tk", "agents/an-agent/AGENT.md", agent_dir, agent_dir / "AGENT.md", errors, []
    )

    assert len(errors) == 1
    assert "__pycache__" in errors[0]


def test_the_shipped_agent_folders_hold_nothing_else() -> None:
    agents = Path(REPO_ROOT) / V.AI_DIR / "dlthub-platform" / "dlthub" / "agents"
    errors: list[str] = []
    for agent_dir in sorted(p for p in agents.iterdir() if p.is_dir()):
        V._validate_shipped_modules(
            "dlthub-platform", f"{agent_dir.name}/AGENT.md", agent_dir,
            agent_dir / "AGENT.md", errors, []
        )

    assert errors == []


def test_an_install_copies_the_module_beside_the_definition(tmp_path: Path) -> None:
    """dlt's own install path, run over this checkout: the agent folder is copied whole, so
    the module the deployment imports reaches the workspace."""
    from dlt._workspace.cli.dlthub.ai.agents import _ClaudeAgent
    from dlt._workspace.cli.dlthub.ai.commands import _execute_install

    source = Path(REPO_ROOT) / V.AI_DIR / "dlthub-platform" / "dlthub" / "agents"
    actions = []
    for agent in ("job-inspector", "job-inspector-eval"):
        actions += _ClaudeAgent().install_actions(
            "agent", source / agent, agent, "dlthub-platform", tmp_path
        )
    _execute_install(actions, project_root=tmp_path)

    installed = sorted(
        str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file()
    )
    assert installed == [
        ".claude/dlthub/agents/job-inspector-eval/AGENT.md",
        ".claude/dlthub/agents/job-inspector-eval/checks.py",
        ".claude/dlthub/agents/job-inspector/AGENT.md",
        ".claude/dlthub/agents/job-inspector/links.py",
    ]


def install_check_errors(tmp_path: Path, drop: str = "") -> list[str]:
    """`lint_install`'s verdict on a workspace built from the real toolkit, minus `drop`."""
    import lint_install as L

    host = tmp_path / ".claude" / L.DLTHUB_AGENTS_DIR
    for name, files in L.shipped_agents("dlthub-platform").items():
        for file in files:
            (host / name / file).parent.mkdir(parents=True, exist_ok=True)
            (host / name / file).write_text("installed")
    if drop:
        target = host / drop
        if target.is_dir():
            for leftover in target.rglob("*"):
                leftover.unlink()
            target.rmdir()
        else:
            target.unlink()
    return L.missing_agent_files(tmp_path, "dlthub-platform")


def test_a_complete_install_is_reported_as_complete(tmp_path):
    assert install_check_errors(tmp_path) == []


def test_an_install_missing_an_agent_module_is_caught(tmp_path):
    """An install once skipped a toolkit's agents and still exited 0:
    https://github.com/dlt-hub/dlt/issues/4454
    """
    errors = install_check_errors(tmp_path, drop="job-inspector/links.py")

    assert errors == ["job-inspector/links.py is not in the workspace"]


def test_an_install_missing_a_whole_agent_is_caught(tmp_path):
    errors = install_check_errors(tmp_path, drop="job-inspector")

    assert errors == ["agent 'job-inspector' is not in the workspace"]
