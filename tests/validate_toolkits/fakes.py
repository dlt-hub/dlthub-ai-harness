"""Toolkit trees the validator tests run against.

`tools/` is a script folder, so it goes on the path the way `make validate-toolkits` runs it.
Not a `conftest.py`: pytest imports them all under one module name and
`tests/job_inspector_eval` already has one.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import validate_toolkits as V  # noqa: E402


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fake_root(tmp_path: Path, agents: list[str]) -> Path:
    """A repo root whose router skill indexes `agents`, each a `toolkit:agent` ref."""
    rows = "\n".join(
        f'x → {ref} | dlthub ai toolkit install {ref.split(":")[0]} | run.agent("{ref}")'
        for ref in agents
    )
    write(
        tmp_path / V._ROUTER_SKILL,
        f"---\nname: dlthub-router\n---\n\n## Background agents\n\n```\n{rows}\n```\n",
    )
    return tmp_path


def toolkit(
    root: Path,
    name: str,
    skills: tuple[str, ...] = (),
    agents: tuple[str, ...] = (),
    workflow_refs: tuple[str, ...] | None = None,
    workflow: bool = True,
    skill_description: str = "d",
) -> None:
    """A minimal toolkit tree. `workflow_refs` defaults to every skill and agent."""
    tk = root / V.AI_DIR / name
    write(tk / ".claude-plugin" / "toolkit.json", '{"dependencies": []}')
    for skill in skills:
        write(
            tk / "skills" / skill / "SKILL.md",
            f"---\nname: {skill}\ndescription: {skill_description}\n---\n",
        )
    for agent in agents:
        write(tk / "agents" / agent / V._AGENT_FILE, f"---\nname: {agent}\n---\n\nprompt\n")
    if workflow:
        refs = skills + agents if workflow_refs is None else workflow_refs
        steps = "\n".join(f"1. **Step** (`{ref}`)" for ref in refs)
        write(tk / "rules" / "workflow.md", f"# {name}\n\n## Core workflow\n{steps}\n")
