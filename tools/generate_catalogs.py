#!/usr/bin/env python3
"""Generate the launcher catalogs for Cursor, Codex and CoCo.

The launcher (dlthub-setup) installs the other toolkits with the dlthub CLI
(dlt-hub/dlthub-ai-harness-internal#128). Add --check to fail on stale files.
CoCo installs a repo root and reads skills/ there, so skills/ links to the launcher.
Format docs: cursor.com, developers.openai.com/codex, snowflake.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = "dlthub-setup"
# CoCo loads skills only from this repo-root folder, a symlink to the launcher.
ROOT_SKILLS = "skills"
_EDIT_HINT = (
    "Do not edit generated files by hand. Edit .claude-plugin/marketplace.json, "
    f"workbench/{LAUNCHER}/.claude-plugin/plugin.json or workbench/{LAUNCHER}/skills/, "
    "then run: uv run python tools/generate_catalogs.py"
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


def dumps(data: dict) -> str:
    """Serialize JSON the way the committed files are formatted."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# Claude directory listing fields and their Codex interface names.
_LISTING_URLS = {
    "documentationUrl": "websiteURL",
    "supportUrl": "supportURL",
    "privacyPolicyUrl": "privacyPolicyURL",
    "termsOfServiceUrl": "termsOfServiceURL",
}


def _listing_urls(plugin: dict) -> dict[str, str]:
    """Return the Codex listing URLs that the Claude plugin.json sets."""
    return {codex: plugin[claude] for claude, codex in _LISTING_URLS.items() if claude in plugin}


def _icons(plugin: dict) -> dict[str, str]:
    """Return the two Codex icons, both set to the Claude listing icon."""
    return {"logo": plugin["icon"], "composerIcon": plugin["icon"]} if "icon" in plugin else {}


def launcher_manifests(plugin: dict) -> dict[str, dict]:
    """Return the Cursor and Codex manifests keyed by path in the launcher folder."""
    meta = {k: plugin[k] for k in _META if k in plugin}
    codex = {
        **meta,
        "skills": "./skills/",
        "interface": {
            "displayName": plugin.get("displayName", plugin["name"]),
            # The Codex directory caps this at 30 characters.
            "shortDescription": "dltHub toolkit launcher",
            "longDescription": plugin["description"],
            "developerName": plugin.get("author", {}).get("name", ""),
            "category": "Data",
            "capabilities": [],
            **_listing_urls(plugin),
            **_icons(plugin),
        },
    }
    return {".cursor-plugin/plugin.json": meta, ".codex-plugin/plugin.json": codex}


def _market_and_entry(root: Path) -> tuple[dict, dict]:
    """Return the Claude catalog and its launcher entry."""
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
    entry = next((p for p in market["plugins"] if p["name"] == LAUNCHER), None)
    if entry is None:
        sys.exit(f"ERROR: no '{LAUNCHER}' entry in .claude-plugin/marketplace.json")
    return market, entry


def skills_link_target(root: Path) -> str:
    """Return the launcher skills folder that the root skills symlink points to."""
    return f"{_market_and_entry(root)[1]['source'].removeprefix('./')}/skills"


def generate(root: Path) -> dict[str, str]:
    """Return the text of each generated file keyed by path relative to root."""
    market, entry = _market_and_entry(root)
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
                    "category": entry.get("category", "data").capitalize(),
                }
            ],
        }),
    }
    rel = entry["source"].removeprefix("./")
    plugin = json.loads((root / rel / ".claude-plugin" / "plugin.json").read_text())
    for name, data in launcher_manifests(plugin).items():
        out[f"{rel}/{name}"] = dumps(data)
    # CoCo reads .cortex-plugin first; root .claude-plugin is only a catalog.
    meta = {k: plugin[k] for k in _META if k in plugin}
    cortex = {**meta, "skills": f"./{ROOT_SKILLS}/"}
    out[".cortex-plugin/plugin.json"] = dumps(cortex)
    return out


def skills_link_ok(out_dir: Path, target: str) -> bool:
    """Return True if the root skills folder is a symlink to the launcher skills."""
    link = out_dir / ROOT_SKILLS
    return link.is_symlink() and os.readlink(link) == target


def write_skills_link(out_dir: Path, target: str) -> None:
    """Replace the root skills folder with a symlink to the launcher skills."""
    link = out_dir / ROOT_SKILLS
    if link.is_symlink() or link.is_file():
        link.unlink()
    elif link.is_dir():
        shutil.rmtree(link)
    link.symlink_to(target, target_is_directory=True)


def report(changed: list[str]) -> int:
    """Print each file that differs from the source and return the exit code."""
    if not changed:
        print("Catalogs are up to date.")
        return 0
    # GitHub Actions shows these lines as errors on the files in the PR.
    ci = os.environ.get("GITHUB_ACTIONS") == "true"
    for rel in changed:
        print(f"::error file={rel}::Generated file. {_EDIT_HINT}" if ci else f"  DIFF  {rel}")
    print(f"These generated files differ from the source. {_EDIT_HINT}")
    return 1


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
    target = skills_link_target(ROOT)
    link_ok = skills_link_ok(args.out, target)
    if args.check:
        sys.exit(report(changed + ([] if link_ok else [ROOT_SKILLS])))
    for rel in changed:
        path = args.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[rel])
        print(f"  wrote {rel}")
    if not link_ok:
        write_skills_link(args.out, target)
        print(f"  linked {ROOT_SKILLS} -> {target}")
    print(f"{len(files)} files, {len(changed)} changed, symlink {'ok' if link_ok else 'fixed'}.")


if __name__ == "__main__":
    main()
