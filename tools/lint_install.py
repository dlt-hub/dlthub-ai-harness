#!/usr/bin/env python3
"""Install all toolkits for every supported agent into temp directories.

Verifies that `dlt ai init` and `dlt ai toolkit <name> install` succeed
for claude, cursor, and codex without errors.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

AGENTS = ["claude", "cursor", "codex"]
REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def get_toolkit_names() -> list[str]:
    data = json.loads(MARKETPLACE.read_text())
    return [p["name"] for p in data["plugins"]]


def run_dlt(args: list[str], cwd: Path) -> tuple[bool, str]:
    cmd = ["uv", "run", "dlt", "--non-interactive"] + args
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

            # dlt ai init
            total += 1
            ok, output = run_dlt(
                ["ai", "init", "--agent", agent, "--location", location],
                cwd=project,
            )
            status = "ok" if ok else "FAIL"
            print(f"  [{agent}] dlt ai init ... {status}")
            if not ok:
                errors.append(f"[{agent}] dlt ai init failed:\n{output}")
                continue

            # each toolkit
            for name in toolkits:
                total += 1
                ok, output = run_dlt(
                    [
                        "ai",
                        "toolkit",
                        name,
                        "install",
                        "--agent",
                        agent,
                        "--location",
                        location,
                        "--overwrite",
                        "--strict",
                    ],
                    cwd=project,
                )
                status = "ok" if ok else "FAIL"
                print(f"  [{agent}] dlt ai toolkit {name} install ... {status}")
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
