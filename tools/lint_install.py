#!/usr/bin/env python3
"""Install all toolkits for every supported agent into temp directories.

Verifies that `dlthub ai init` and `dlthub ai toolkit install <name>` succeed for claude,
cursor, codex and cortex without errors, that a toolkit hidden from an agent is refused, and
that the MCP feature groups a toolkit adds reach the agent's MCP config.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

AGENTS = ["claude", "cursor", "codex", "cortex"]
REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
AI_DIR = REPO_ROOT / "workbench"
# where each agent reads the MCP server from, relative to the project or to $SNOWFLAKE_HOME
MCP_CONFIGS = {
    "claude": [".mcp.json"],
    "cursor": [".cursor/mcp.json"],
    "codex": [".codex/config.toml"],
    "cortex": [".cortex/mcp.json", "$SNOWFLAKE_HOME/cortex/mcp.json"],
}


def get_toolkit_names() -> list[str]:
    data = json.loads(MARKETPLACE.read_text())
    return [p["name"] for p in data["plugins"]]


def toolkit_meta(name: str) -> dict:
    path = AI_DIR / name / ".claude-plugin" / "toolkit.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def is_visible(meta: dict, agent: str) -> bool:
    """The same rule as dlt's `is_visible`: only `include`, or all but `exclude`."""
    visibility = meta.get("agents") or {}
    if "include" in visibility:
        return agent in visibility["include"]
    return agent not in visibility.get("exclude", [])


def run_dlt(args: list[str], cwd: Path, env: dict[str, str]) -> tuple[bool, str]:
    cmd = ["uv", "run", "dlthub", "--non-interactive"] + args
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120, env=env)
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def missing_features(agent: str, project: Path, snowflake_home: Path, features: dict) -> list[str]:
    """Feature groups of `features` that no MCP config of the agent names."""
    missing = []
    for rel in MCP_CONFIGS[agent]:
        path = Path(rel.replace("$SNOWFLAKE_HOME", str(snowflake_home)))
        path = path if path.is_absolute() else project / path
        text = path.read_text() if path.is_file() else ""
        for server, names in features.items():
            missing += [f"{path.name}: {server} {n}" for n in names if n.lstrip("+") not in text]
    return missing


def main() -> int:
    toolkits = get_toolkit_names()
    location = str(REPO_ROOT)
    errors: list[str] = []
    total = 0

    for agent in AGENTS:
        with tempfile.TemporaryDirectory(prefix=f"lint-{agent}-") as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            # the cortex agent also writes the user MCP config, keep it out of the real home
            snowflake_home = Path(tmpdir) / "snowflake-home"
            env = {**os.environ, "SNOWFLAKE_HOME": str(snowflake_home)}

            total += 1
            ok, output = run_dlt(
                ["ai", "init", "--agent", agent, "--location", location], cwd=project, env=env
            )
            status = "ok" if ok else "FAIL"
            print(f"  [{agent}] dlthub ai init ... {status}")
            if not ok:
                errors.append(f"[{agent}] dlthub ai init failed:\n{output}")
                continue

            for name in toolkits:
                total += 1
                meta = toolkit_meta(name)
                visible = is_visible(meta, agent)
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
                    env=env,
                )
                if not visible:
                    status = "refused" if not ok else "FAIL"
                    print(f"  [{agent}] dlthub ai toolkit install {name} (hidden) ... {status}")
                    if ok:
                        errors.append(f"[{agent}] toolkit {name} is hidden but installed")
                    continue
                status = "ok" if ok else "FAIL"
                print(f"  [{agent}] dlthub ai toolkit install {name} ... {status}")
                if not ok:
                    errors.append(f"[{agent}] toolkit {name} install failed:\n{output}")
                    continue
                if missing := missing_features(
                    agent, project, snowflake_home, meta.get("mcp_features", {})
                ):
                    errors.append(f"[{agent}] toolkit {name} MCP features not in config: {missing}")

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
