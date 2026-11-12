#!/usr/bin/env python3
"""Generate the Cursor, Copilot and Codex catalogs for the launcher plugin only.

The launcher (bootstrap) installs the other toolkits with the dlthub CLI
(dlt-hub/dlthub-ai-harness-internal#128). Add --check to fail on stale files.
Formats: https://cursor.com/docs/reference/plugins and
https://developers.openai.com/codex/plugins/build; Copilot reads the Claude one.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = "bootstrap"
# Fields copied from the Claude plugin.json into every host manifest.
_META = (
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
)


def dumps(data: dict) -> str:
    """Serialize JSON the way the committed files are formatted."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def launcher_manifests(plugin: dict) -> dict[str, dict]:
    """Return the Cursor and Codex manifests keyed by path in the launcher folder."""
    meta = {k: plugin[k] for k in _META if k in plugin}
    codex = {
        **meta,
        "skills": "./skills/",
        "interface": {
            "displayName": plugin["name"],
            # The Codex directory caps this at 30 characters.
            "shortDescription": "dltHub toolkit launcher",
            "longDescription": plugin["description"],
            "developerName": plugin.get("author", {}).get("name", ""),
            "category": "Data",
            "capabilities": [],
        },
    }
    return {".cursor-plugin/plugin.json": meta, ".codex-plugin/plugin.json": codex}


def generate(root: Path) -> dict[str, str]:
    """Return the text of each generated file keyed by path relative to root."""
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["name"] == LAUNCHER)
    # Copilot and Cursor read the Claude catalog format as is.
    claude_format = dumps({**market, "plugins": [entry]})
    out = {
        ".github/plugin/marketplace.json": claude_format,
        ".cursor-plugin/marketplace.json": claude_format,
        ".agents/plugins/marketplace.json": dumps({
            "name": market["name"],
            "interface": {"displayName": market["name"]},
            "plugins": [
                {
                    "name": entry["name"],
                    "source": {"source": "local", "path": entry["source"]},
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": entry.get("category", "data").capitalize(),
                }
            ],
        }),
    }
    rel = entry["source"].removeprefix("./")
    plugin = json.loads((root / rel / ".claude-plugin" / "plugin.json").read_text())
    for name, data in launcher_manifests(plugin).items():
        out[f"{rel}/{name}"] = dumps(data)
    return out


def main() -> None:
    """Write the generated files, or with --check report the stale ones."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a file is stale")
    ap.add_argument("--out", type=Path, default=ROOT, help="write under this folder")
    args = ap.parse_args()

    files = generate(ROOT)
    changed = [
        rel
        for rel, text in files.items()
        if not (args.out / rel).exists() or (args.out / rel).read_text() != text
    ]
    if args.check:
        for rel in changed:
            print(f"  DIFF  {rel}")
        if changed:
            print("Run: uv run python tools/generate_catalogs.py")
        else:
            print("Catalogs are up to date.")
        sys.exit(1 if changed else 0)
    for rel in changed:
        path = args.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[rel])
        print(f"  wrote {rel}")
    print(f"{len(files)} files, {len(changed)} changed.")


if __name__ == "__main__":
    main()
