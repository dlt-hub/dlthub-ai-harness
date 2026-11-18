#!/usr/bin/env python3
"""Install all toolkits for every supported agent into temp directories.

Verifies that `dlthub ai init` and `dlthub ai toolkit install <name>` succeed
for claude, cursor, codex and cortex without errors.
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


def get_toolkit_names() -> list[str]:
    data = json.loads(MARKETPLACE.read_text())
    return [p["name"] for p in data["plugins"]]


def isolated_env(home: Path) -> dict[str, str]:
    """Return an env whose HOME is a temp folder, so no install writes user config."""
    uv_cache = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True).stdout.strip()
    # The cortex agent reads SNOWFLAKE_HOME before HOME.
    env = {k: v for k, v in os.environ.items() if k != "SNOWFLAKE_HOME"}
    return {**env, "HOME": str(home), "UV_CACHE_DIR": uv_cache}


def run_dlt(args: list[str], cwd: Path, env: dict[str, str]) -> tuple[bool, str]:
    cmd = ["uv", "run", "dlthub", "--non-interactive"] + args
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def main() -> int:
    toolkits = get_toolkit_names()
    location = str(REPO_ROOT)
    errors: list[str] = []
    total = 0

    for agent in AGENTS:
        with tempfile.TemporaryDirectory(prefix=f"lint-{agent}-") as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            env = isolated_env(Path(tmpdir) / "home")

            total += 1
            ok, output = run_dlt(
                ["ai", "init", "--agent", agent, "--location", location],
                cwd=project,
                env=env,
            )
            status = "ok" if ok else "FAIL"
            print(f"  [{agent}] dlthub ai init ... {status}")
            if not ok:
                errors.append(f"[{agent}] dlthub ai init failed:\n{output}")
                continue

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
                    env=env,
                )
                status = "ok" if ok else "FAIL"
                print(f"  [{agent}] dlthub ai toolkit install {name} ... {status}")
                if not ok:
                    errors.append(f"[{agent}] toolkit {name} install failed:\n{output}")

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
