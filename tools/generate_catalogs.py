#!/usr/bin/env python3
"""Generate the Cursor, Copilot, Codex and Gemini catalogs for the launcher.

The launcher (bootstrap) installs the other toolkits with the dlthub CLI
(dlt-hub/dlthub-ai-harness-internal#128). Add --check to fail on stale files.
Gemini installs only a repo root and reads skills/ there, so we copy the skills.
Copilot reads the Claude format. Cursor, Codex and Gemini formats are at
cursor.com/docs/reference/plugins, developers.openai.com/codex/plugins/build
and geminicli.com/docs/extensions/reference.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = "bootstrap"
# Gemini loads skills only from this folder at the extension (repo) root.
GEMINI_SKILLS = "skills"
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
    entry = next((p for p in market["plugins"] if p["name"] == LAUNCHER), None)
    if entry is None:
        sys.exit(f"ERROR: no '{LAUNCHER}' entry in .claude-plugin/marketplace.json")
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
    out["gemini-extension.json"] = dumps({
        "name": market["name"],
        "version": plugin["version"],
        "description": plugin["description"],
    })
    skills_dir = root / rel / "skills"
    for path in sorted(p for p in skills_dir.rglob("*") if p.is_file()):
        out[f"{GEMINI_SKILLS}/{path.relative_to(skills_dir)}"] = path.read_text()
    return out


def stale_copies(out_dir: Path, files: dict[str, str]) -> list[str]:
    """Return files in the Gemini skills folder that the generator no longer makes."""
    skills_dir = out_dir / GEMINI_SKILLS
    found = (p for p in skills_dir.rglob("*") if p.is_file())
    return sorted(rel for p in found if (rel := str(p.relative_to(out_dir))) not in files)


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
    stale = stale_copies(args.out, files)
    if args.check:
        for rel in changed:
            print(f"  DIFF  {rel}")
        for rel in stale:
            print(f"  STALE {rel}")
        if changed or stale:
            print("Run: uv run python tools/generate_catalogs.py")
        else:
            print("Catalogs are up to date.")
        sys.exit(1 if changed or stale else 0)
    for rel in changed:
        path = args.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[rel])
        print(f"  wrote {rel}")
    for rel in stale:
        (args.out / rel).unlink()
        print(f"  removed {rel}")
    print(f"{len(files)} files, {len(changed)} changed, {len(stale)} removed.")


if __name__ == "__main__":
    main()
