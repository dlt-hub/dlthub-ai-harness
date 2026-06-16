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

Each workspace is always recreated from scratch.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals" / ".evals"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, printing it first."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0 and check:
        print(f"  STDOUT: {result.stdout.strip()}")
        print(f"  STDERR: {result.stderr.strip()}")
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")
    return result


def get_dlt_version() -> str:
    """Get dlt version from current environment."""
    result = subprocess.run(
        ["uv", "run", "python", "-c", "import dlt; print(dlt.__version__)"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    raise RuntimeError("Cannot detect dlt version from current environment")


def ws_name_for(eval_dir: Path, workspace_id: str, agent: str = "claude") -> str:
    """Build workspace directory name: toolkit--skill--workspace_id[--agent].

    The agent suffix is omitted for claude so existing claude workspace paths
    (and run_trigger_eval.py's matching convention) stay unchanged; cursor/codex
    get a suffix so all three agents can coexist for the same eval.
    """
    rel = eval_dir.relative_to(ROOT / "evals")
    name = str(rel).replace("/", "--").replace("\\", "--") + "--" + workspace_id
    if agent != "claude":
        name += "--" + agent
    return name


def create_single_workspace(
    workspace: Path, dlt_pkg: str, toolkits: list[str], agent: str = "claude"
) -> Path:
    """Create a single eval workspace."""
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    # Check uv
    result = run(["uv", "--version"], cwd=workspace, check=False)
    if result.returncode != 0:
        print("ERROR: uv is not installed")
        sys.exit(1)

    # Create venv + install dlt. Also install `dlthub[mcp]` (the workspace MCP
    # server lives there), mirroring a real scaffolded workspace.
    run(["uv", "venv"], cwd=workspace)
    run(["uv", "pip", "install", dlt_pkg, "dlthub[mcp]"], cwd=workspace)

    # Resolve the CLI name. The rebranded `dlthub` console script only ships on
    # newer dlt builds; published PyPI releases still expose the CLI as `dlt`.
    # Both provide identical `ai` subcommands, so fall back to `dlt`.
    cli = "dlthub"
    result = run(["uv", "run", cli, "--version"], cwd=workspace, check=False)
    if result.returncode != 0:
        cli = "dlt"
        result = run(["uv", "run", cli, "--version"], cwd=workspace)
    print(f"  cli: {cli} ({result.stdout.strip()})")

    # AI init — install the LOCAL toolkits from this repo (via --location) so
    # the eval tests working-tree changes, not the published dlthub snapshot.
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

    # Install toolkits. Canonical syntax is install-first: `ai toolkit install <name>`
    # (per the dlthub CLI docs). The older published `dlt` binary parses name-first
    # (`ai toolkit <name> install`) and rejects install-first, so fall back to it —
    # mirroring the dlthub->dlt CLI fallback above.
    base = ["uv", "run", cli, "--non-interactive", "ai", "toolkit"]
    tail = ["--agent", agent, "--location", str(ROOT)]
    for toolkit in toolkits:
        print(f"  Installing toolkit: {toolkit}")
        result = run(base + ["install", toolkit] + tail, cwd=workspace, check=False)
        if result.returncode != 0:
            # older binary: retry with name-first ordering
            run(base + [toolkit, "install"] + tail, cwd=workspace)

    return workspace


def report_workspace(workspace: Path, agent: str = "claude") -> None:
    """Print workspace contents for the agent's install layout."""
    # Skills land under a per-agent root: .claude/.cursor/.agents.
    skills_root = {"claude": ".claude", "cursor": ".cursor", "codex": ".agents"}[agent]
    skills_dir = workspace / skills_root / "skills"
    if skills_dir.is_dir():
        skills = [d.name for d in sorted(skills_dir.iterdir()) if d.is_dir()]
        print(f"  skills: {', '.join(skills) if skills else '(none)'}")

    # Rules: claude .claude/rules/*.md, cursor .cursor/rules/*.mdc; on codex
    # rules are folded into the always-loaded AGENTS.md (no rules dir).
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

    # Support both old single-workspace and new multi-workspace format
    workspaces_config = config.get(".eval-workspaces")
    if workspaces_config is None:
        # Legacy: single workspace
        ws_config = config.get(".eval-workspace", {})
        workspaces_config = {"default": ws_config}

    dlt_version = get_dlt_version()
    dlt_pkg = f"dlt[hub]=={dlt_version}"
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
    parser = argparse.ArgumentParser(
        description="Create eval workspaces for trigger testing."
    )
    parser.add_argument(
        "eval_dir", help="Eval directory, e.g. evals/init/dlthub-router"
    )
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
