#!/usr/bin/env python3
"""Create eval workspaces for trigger testing.

Reads config.json from an eval directory and creates fresh workspaces under
evals/.evals/ for each workspace definition.

Usage:
    python tools/create_eval_workspace.py evals/init/toolkit-dispatch

config.json format:
    {
        ".eval-workspaces": {
            "init-only": {"toolkits": []},
            "with-rest-api": {"toolkits": ["rest-api-pipeline"]}
        }
    }

Each workspace is always recreated from scratch.
"""

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


def ws_name_for(eval_dir: Path, workspace_id: str) -> str:
    """Build workspace directory name: toolkit--skill--workspace_id."""
    rel = eval_dir.relative_to(ROOT / "evals")
    return str(rel).replace("/", "--").replace("\\", "--") + "--" + workspace_id


def create_single_workspace(workspace: Path, dlt_pkg: str, toolkits: list[str]) -> Path:
    """Create a single eval workspace."""
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    # Check uv
    result = run(["uv", "--version"], cwd=workspace, check=False)
    if result.returncode != 0:
        print("ERROR: uv is not installed")
        sys.exit(1)

    # Create venv + install dlt
    run(["uv", "venv"], cwd=workspace)
    run(["uv", "pip", "install", dlt_pkg], cwd=workspace)

    # Verify
    result = run(["uv", "run", "dlt", "--version"], cwd=workspace)
    print(f"  dlt: {result.stdout.strip()}")

    # AI init
    run(
        ["uv", "run", "dlt", "--non-interactive", "ai", "init", "--agent", "claude"],
        cwd=workspace,
    )

    # Install toolkits
    for toolkit in toolkits:
        print(f"  Installing toolkit: {toolkit}")
        run(
            [
                "uv",
                "run",
                "dlt",
                "--non-interactive",
                "ai",
                "toolkit",
                toolkit,
                "install",
                "--agent",
                "claude",
            ],
            cwd=workspace,
        )

    return workspace


def report_workspace(workspace: Path) -> None:
    """Print workspace contents."""
    skills_dir = workspace / ".claude" / "skills"
    if skills_dir.is_dir():
        skills = [d.name for d in sorted(skills_dir.iterdir()) if d.is_dir()]
        print(f"  skills: {', '.join(skills) if skills else '(none)'}")

    rules_dir = workspace / ".claude" / "rules"
    if rules_dir.is_dir():
        rules = [f.name for f in sorted(rules_dir.iterdir()) if f.suffix == ".md"]
        print(f"  rules:  {', '.join(rules) if rules else '(none)'}")


def create_workspaces(eval_dir: Path) -> list[Path]:
    """Create all workspaces defined in config.json."""
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
    dlt_pkg = f"dlt[workspace]=={dlt_version}"
    EVALS_DIR.mkdir(parents=True, exist_ok=True)

    created = []
    for ws_id, ws_config in workspaces_config.items():
        toolkits = ws_config.get("toolkits", [])
        name = ws_name_for(eval_dir, ws_id)
        workspace = EVALS_DIR / name

        print(f"\n=== Workspace: {ws_id} ===")
        print(f"  path: {workspace}")
        print(f"  dlt: {dlt_pkg}")
        print(f"  toolkits: {toolkits or '(init only)'}")

        create_single_workspace(workspace, dlt_pkg, toolkits)
        report_workspace(workspace)
        created.append(workspace)

    return created


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <eval-dir>")
        print(f"  e.g.: {sys.argv[0]} evals/init/toolkit-dispatch")
        sys.exit(1)

    eval_dir = Path(sys.argv[1])
    if not eval_dir.is_absolute():
        eval_dir = ROOT / eval_dir

    if not eval_dir.is_dir():
        print(f"ERROR: {eval_dir} is not a directory")
        sys.exit(1)

    workspaces = create_workspaces(eval_dir)
    print(f"\n{len(workspaces)} workspace(s) created:")
    for ws in workspaces:
        print(f"  {ws}")


if __name__ == "__main__":
    main()
