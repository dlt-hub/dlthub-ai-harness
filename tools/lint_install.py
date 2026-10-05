#!/usr/bin/env python3
"""Install all toolkits for every supported agent into temp directories.

Verifies that `dlthub ai init` and `dlthub ai toolkit install <name>` succeed
for claude, cursor, and codex without errors, and that every file of every agent
the toolkit ships arrives in the installed workspace.

An exit code alone would not have caught https://github.com/dlt-hub/dlt/issues/4454,
where an install walked the wrong directory and skipped the agents without failing.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# where a toolkit keeps its agents and where an install puts them, dlt's own constant
from dlt._workspace.cli.dlthub.ai.utils import DLTHUB_AGENTS_DIR

AGENTS = ["claude", "cursor", "codex"]
REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def get_toolkit_names() -> list[str]:
    data = json.loads(MARKETPLACE.read_text())
    return [p["name"] for p in data["plugins"]]


def shipped_agents(toolkit: str) -> dict[str, list[str]]:
    """File names per agent the toolkit ships, keyed by agent name."""
    agents_dir = REPO_ROOT / "workbench" / toolkit / DLTHUB_AGENTS_DIR
    if not agents_dir.is_dir():
        return {}
    return {
        d.name: sorted(f.name for f in d.rglob("*") if f.is_file())
        for d in sorted(agents_dir.iterdir())
        if d.is_dir()
    }


def missing_agent_files(project: Path, toolkit: str) -> list[str]:
    """What the install owed the workspace and did not put there.

    The host folder differs per agent, so the glob asks only for the path dlt installs under.
    """
    missing = []
    for name, files in shipped_agents(toolkit).items():
        installed = list(project.glob(f"*/{DLTHUB_AGENTS_DIR}/{name}"))
        if not installed:
            missing.append(f"agent {name!r} is not in the workspace")
            continue
        landed = {f.name for f in installed[0].rglob("*") if f.is_file()}
        missing += [f"{name}/{f} is not in the workspace" for f in files if f not in landed]
    return missing


def run_dlt(args: list[str], cwd: Path) -> tuple[bool, str]:
    cmd = ["uv", "run", "dlthub", "--non-interactive"] + args
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def main() -> int:
    toolkits = get_toolkit_names()
    location = str(REPO_ROOT)
    errors: list[str] = []
    total = 0

    for agent in AGENTS:
        with tempfile.TemporaryDirectory(prefix=f"lint-{agent}-") as tmpdir:
            project = Path(tmpdir)

            # dlthub ai init
            total += 1
            ok, output = run_dlt(
                ["ai", "init", "--agent", agent, "--location", location],
                cwd=project,
            )
            status = "ok" if ok else "FAIL"
            print(f"  [{agent}] dlthub ai init ... {status}")
            if not ok:
                errors.append(f"[{agent}] dlthub ai init failed:\n{output}")
                continue

            # each toolkit
            for name in toolkits:
                total += 1
                ok, output = run_dlt(
                    [
                        "ai",
                        "toolkit",
                        "install",
                        name,
                        "--agent",
                        agent,
                        "--location",
                        location,
                        "--overwrite",
                        "--strict",
                    ],
                    cwd=project,
                )
                missing = missing_agent_files(project, name) if ok else []
                status = "ok" if ok and not missing else "FAIL"
                print(f"  [{agent}] dlthub ai toolkit install {name} ... {status}")
                if not ok:
                    errors.append(f"[{agent}] toolkit {name} install failed:\n{output}")
                elif missing:
                    errors.append(
                        f"[{agent}] toolkit {name} installed without its agents:\n  "
                        + "\n  ".join(missing)
                    )

    print()
    if errors:
        print(f"FAILED: {len(errors)}/{total}")
        for e in errors:
            print(f"\n  {e}")
        return 1
    else:
        print(
            f"All {total} installs passed ({len(AGENTS)} agents x {len(toolkits)} toolkits + init)"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
