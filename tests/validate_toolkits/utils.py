import json
from pathlib import Path

from tools import validate_toolkits as V


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fake_root(tmp_path: Path, toolkits: list[str], platform_row: bool = True) -> Path:
    """A repo root whose router skill indexes `toolkits`, plus the platform toolkit row."""
    rows = [f"intent → {V._INDEX_HEADER} | entry skill"]
    rows += [f"x → {name} | entry" for name in toolkits]
    if platform_row:
        rows.append("deploy → a platform toolkit | its workflow entry")
    write(
        tmp_path / V._ROUTER_SKILL,
        "---\nname: dlthub-router\n---\n\n## Toolkits\n\n```\n" + "\n".join(rows) + "\n```\n",
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
    dependencies: tuple[str, ...] = (),
    description: str = "d",
    listed: bool = True,
    skill_body: str = "",
) -> None:
    """A minimal toolkit tree. `workflow_refs` defaults to every skill and agent."""
    tk = root / V.AI_DIR / name
    meta: dict = {"dependencies": list(dependencies)}
    if not listed:
        meta["listed"] = False
    write(tk / ".claude-plugin" / "toolkit.json", json.dumps(meta))
    write(
        tk / ".claude-plugin" / "plugin.json",
        json.dumps({"name": name, "description": description, "version": "0.1.0"}),
    )
    for skill in skills:
        write(
            tk / "skills" / skill / "SKILL.md",
            f"---\nname: {skill}\ndescription: {skill_description}\n---\n{skill_body}",
        )
    for agent in agents:
        write(tk / V._AGENTS_PATH / agent / V._AGENT_FILE, f"---\nname: {agent}\n---\n\nprompt\n")
    if workflow:
        refs = skills + agents if workflow_refs is None else workflow_refs
        steps = "\n".join(f"1. **Step** (`{ref}`)" for ref in refs)
        write(tk / "rules" / "workflow.md", f"# {name}\n\n## Core workflow\n{steps}\n")
