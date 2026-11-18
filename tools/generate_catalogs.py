#!/usr/bin/env python3
"""Generate the launcher catalogs for Cursor, Codex and CoCo.

The launcher (dlthub-setup) installs the other toolkits with the dlthub CLI.
CoCo installs a repo root and reads skills/ there, so we copy them.
Add --check to fail on stale files.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = "dlthub-setup"
# CoCo loads skills only from this folder at the repo root.
ROOT_SKILLS = "skills"
_EDIT_HINT = (
    "Do not edit generated files by hand. Edit .claude-plugin/marketplace.json, "
    f"workbench/{LAUNCHER}/.claude-plugin/plugin.json or workbench/{LAUNCHER}/skills/, "
    "git add new skill files, then run: uv run python tools/generate_catalogs.py"
)
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
# Claude directory listing fields and their Codex interface names.
_LISTING_URLS = {
    "documentationUrl": "websiteURL",
    "supportUrl": "supportURL",
    "privacyPolicyUrl": "privacyPolicyURL",
    "termsOfServiceUrl": "termsOfServiceURL",
}


def dumps(data: dict) -> str:
    """Serialize JSON the way the committed files are formatted."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def meta_of(plugin: dict) -> dict:
    """Return the _META fields that the Claude plugin.json sets."""
    return {k: plugin[k] for k in _META if k in plugin}


def launcher_manifests(plugin: dict) -> dict[str, dict]:
    """Return the Cursor and Codex manifests keyed by path in the launcher folder."""
    codex = {
        **meta_of(plugin),
        "skills": "./skills/",
        "interface": {
            "displayName": plugin["displayName"],
            # The Codex directory caps this at 30 characters.
            "shortDescription": "dltHub toolkit launcher",
            "longDescription": plugin["description"],
            "developerName": plugin["author"]["name"],
            "category": "Data",
            "capabilities": [],
            **{codex: plugin[claude] for claude, codex in _LISTING_URLS.items()},
            "logo": plugin["icon"],
            "composerIcon": plugin["icon"],
        },
    }
    return {".cursor-plugin/plugin.json": meta_of(plugin), ".codex-plugin/plugin.json": codex}


def generate(root: Path) -> dict[str, str]:
    """Return the text of each generated file keyed by path relative to root."""
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
    entry = next((p for p in market["plugins"] if p["name"] == LAUNCHER), None)
    if entry is None:
        sys.exit(f"ERROR: no '{LAUNCHER}' entry in .claude-plugin/marketplace.json")
    out = {
        # Cursor reads the Claude catalog format as is.
        ".cursor-plugin/marketplace.json": dumps({**market, "plugins": [entry]}),
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
                    "category": entry["category"].capitalize(),
                }
            ],
        }),
    }
    rel = entry["source"].removeprefix("./")
    plugin = json.loads((root / rel / ".claude-plugin" / "plugin.json").read_text())
    for name, data in launcher_manifests(plugin).items():
        out[f"{rel}/{name}"] = dumps(data)
    # CoCo reads .cortex-plugin first; root .claude-plugin is only a catalog.
    out[".cortex-plugin/plugin.json"] = dumps({**meta_of(plugin), "skills": f"./{ROOT_SKILLS}/"})
    skills_dir = root / rel / "skills"
    for path in tracked_files(root, skills_dir):
        out[f"{ROOT_SKILLS}/{path.relative_to(skills_dir)}"] = path.read_text()
    return out


def tracked_files(root: Path, folder: Path) -> list[Path]:
    """Return the files under folder that git tracks, so local junk is not copied."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", str(folder.relative_to(root))],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(root / rel for rel in listed.split("\0") if rel)


def stale_copies(root: Path, files: dict[str, str]) -> list[str]:
    """Return files in the root skills folder that the generator no longer makes."""
    found = (p for p in (root / ROOT_SKILLS).rglob("*") if p.is_file())
    return sorted(rel for p in found if (rel := str(p.relative_to(root))) not in files)


def report(changed: list[str], stale: list[str]) -> int:
    """Print each file that differs from the source and return the exit code."""
    if not changed and not stale:
        print("Catalogs are up to date.")
        return 0
    # GitHub Actions shows these lines as errors on the files in the PR.
    ci = os.environ.get("GITHUB_ACTIONS") == "true"
    for rel in changed + stale:
        print(f"::error file={rel}::Generated file. {_EDIT_HINT}" if ci else f"  DIFF  {rel}")
    print(f"These generated files differ from the source. {_EDIT_HINT}")
    return 1


def main() -> None:
    """Write the generated files, or with --check report the stale ones."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a file is stale")
    args = ap.parse_args()

    files = generate(ROOT)
    changed = [
        rel
        for rel, text in files.items()
        if not (ROOT / rel).exists() or (ROOT / rel).read_text() != text
    ]
    stale = stale_copies(ROOT, files)
    if args.check:
        sys.exit(report(changed, stale))
    for rel in changed:
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[rel])
        print(f"  wrote {rel}")
    for rel in stale:
        (ROOT / rel).unlink()
        print(f"  removed {rel}")
    print(f"{len(files)} files, {len(changed)} changed, {len(stale)} removed.")


if __name__ == "__main__":
    main()
