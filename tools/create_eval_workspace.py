#!/usr/bin/env python3
"""Create eval workspaces for trigger testing.

Reads config.json from an eval directory and creates fresh workspaces under
evals/.evals/ for each workspace definition.

Usage:
    python tools/create_eval_workspace.py evals/init/dlthub-router

config.json format:
    {
        ".eval-workspaces": {
            "init-only": {"toolkits": []},
            "with-rest-api": {"toolkits": ["rest-api-pipeline"]}
        }
    }
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals" / ".evals"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, printing it first."""
    print(f"  $ {' '.join(cmd)}")
    # under `uv run` VIRTUAL_ENV names the workbench venv: drop it, so that
    # uv pip install targets the venv of the workspace
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if result.returncode != 0 and check:
        print(f"  STDOUT: {result.stdout.strip()}")
        print(f"  STDERR: {result.stderr.strip()}")
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")
    return result


def get_dlt_spec() -> str:
    """The dlt requirement of the current environment.

    An unreleased dlt comes from a URL or a local path (`[tool.uv.sources]`), so the eval workspace
    installs it from there. A released one installs by version.
    """
    script = (
        "import importlib.metadata as m; d = m.distribution('dlt');"
        " print(d.version); print(d.read_text('direct_url.json') or '')"
    )
    result = subprocess.run(
        ["uv", "run", "python", "-c", script], capture_output=True, text=True, cwd=ROOT
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("The dlt version in the current environment is not available.")
    version, _, direct_url = result.stdout.partition("\n")
    if not direct_url.strip():
        return f"dlt=={version.strip()}"
    info = json.loads(direct_url)
    url: str = info["url"]
    if url.startswith("file://") and info.get("dir_info", {}).get("editable"):
        return url.removeprefix("file://")
    if vcs := info.get("vcs_info"):
        return f"dlt @ {vcs['vcs']}+{url}@{vcs['commit_id']}"
    return f"dlt @ {url}"


def ws_name_for(eval_dir: Path, workspace_id: str, agent: str = "claude") -> str:
    """Workspace directory name: `toolkit--skill--workspace_id[--agent]`, no suffix for claude."""
    rel = eval_dir.relative_to(ROOT / "evals")
    name = str(rel).replace("/", "--").replace("\\", "--") + "--" + workspace_id
    if agent != "claude":
        name += "--" + agent
    return name


def create_single_workspace(
    workspace: Path, dlt_pkg: str, toolkits: list[str], agent: str = "claude"
) -> Path:
    """Recreate an eval workspace with dlt and the given toolkits installed."""
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    result = run(["uv", "--version"], cwd=workspace, check=False)
    if result.returncode != 0:
        print("ERROR: uv is not installed")
        sys.exit(1)

    # dlthub[mcp] holds the workspace MCP server, as in a scaffolded workspace
    run(["uv", "venv"], cwd=workspace)
    run(["uv", "pip", "install", dlt_pkg, "dlthub[mcp]"], cwd=workspace)

    # older dlt releases ship the CLI as dlt, not dlthub
    cli = "dlthub"
    result = run(["uv", "run", cli, "--version"], cwd=workspace, check=False)
    if result.returncode != 0:
        cli = "dlt"
        result = run(["uv", "run", cli, "--version"], cwd=workspace)
    print(f"  cli: {cli} ({result.stdout.strip()})")

    # --location installs the toolkits of this working tree, not the published ones
    run(
        [
            "uv",
            "run",
            cli,
            "--non-interactive",
            "ai",
            "init",
            "--agent",
            agent,
            "--location",
            str(ROOT),
        ],
        cwd=workspace,
    )

    # the older dlt binary takes the name first: ai toolkit <name> install
    base = ["uv", "run", cli, "--non-interactive", "ai", "toolkit"]
    tail = ["--agent", agent, "--location", str(ROOT)]
    for toolkit in toolkits:
        print(f"  Installing toolkit: {toolkit}")
        result = run(base + ["install", toolkit] + tail, cwd=workspace, check=False)
        if result.returncode != 0:
            run(base + [toolkit, "install"] + tail, cwd=workspace)

    return workspace


def report_workspace(workspace: Path, agent: str = "claude") -> None:
    """Print workspace contents for the agent's install layout."""
    skills_root = {"claude": ".claude", "cursor": ".cursor", "codex": ".agents"}[agent]
    skills_dir = workspace / skills_root / "skills"
    if skills_dir.is_dir():
        skills = [d.name for d in sorted(skills_dir.iterdir()) if d.is_dir()]
        print(f"  skills: {', '.join(skills) if skills else '(none)'}")

    # codex has no rules dir, its rules are folded into the always-loaded AGENTS.md
    if agent == "codex":
        agents_md = workspace / "AGENTS.md"
        print(f"  AGENTS.md: {'present' if agents_md.is_file() else '(missing)'}")
        return
    rules_dir = workspace / skills_root / "rules"
    rule_suffix = ".mdc" if agent == "cursor" else ".md"
    if rules_dir.is_dir():
        rules = [f.name for f in sorted(rules_dir.iterdir()) if f.suffix == rule_suffix]
        print(f"  rules:  {', '.join(rules) if rules else '(none)'}")


def create_workspaces(eval_dir: Path, agent: str = "claude") -> list[Path]:
    """Create all workspaces defined in config.json for the given agent."""
    config_path = eval_dir / "config.json"
    if not config_path.exists():
        print(f"ERROR: {config_path} not found")
        sys.exit(1)

    config = json.loads(config_path.read_text())

    workspaces_config = config.get(".eval-workspaces")
    if workspaces_config is None:
        # legacy configs hold a single ".eval-workspace"
        ws_config = config.get(".eval-workspace", {})
        workspaces_config = {"default": ws_config}

    dlt_pkg = get_dlt_spec()
    EVALS_DIR.mkdir(parents=True, exist_ok=True)

    created = []
    for ws_id, ws_config in workspaces_config.items():
        toolkits = ws_config.get("toolkits", [])
        name = ws_name_for(eval_dir, ws_id, agent)
        workspace = EVALS_DIR / name

        print(f"\n=== Workspace: {ws_id} (agent={agent}) ===")
        print(f"  path: {workspace}")
        print(f"  dlt: {dlt_pkg}")
        print(f"  toolkits: {toolkits or '(init only)'}")

        create_single_workspace(workspace, dlt_pkg, toolkits, agent)
        report_workspace(workspace, agent)
        created.append(workspace)

    return created


def main():
    parser = argparse.ArgumentParser(description="Create eval workspaces for trigger testing.")
    parser.add_argument("eval_dir", help="Eval directory, e.g. evals/init/dlthub-router")
    parser.add_argument(
        "--agent",
        default="claude",
        choices=["claude", "cursor", "codex"],
        help="Agent to initialize the workspaces for (default: claude)",
    )
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir)
    if not eval_dir.is_absolute():
        eval_dir = ROOT / eval_dir

    if not eval_dir.is_dir():
        print(f"ERROR: {eval_dir} is not a directory")
        sys.exit(1)

    workspaces = create_workspaces(eval_dir, args.agent)
    print(f"\n{len(workspaces)} workspace(s) created (agent={args.agent}):")
    for ws in workspaces:
        print(f"  {ws}")


if __name__ == "__main__":
    main()
