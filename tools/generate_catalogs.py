#!/usr/bin/env python3
"""Generate the launcher catalogs for Cursor and Codex.

The launcher (dlthub-setup) installs the other toolkits with the dlthub CLI.
Add --check to fail on stale files. Both modes also fail when the launcher
breaks a rule of the Codex (OpenAI) plugin directory.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = "dlthub-setup"
_EDIT_HINT = (
    "Do not edit generated files by hand. Edit .claude-plugin/marketplace.json, "
    f"workbench/{LAUNCHER}/.claude-plugin/plugin.json, "
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
# Claude directory listing fields and their Codex interface names.
_LISTING_URLS = {
    "documentationUrl": "websiteURL",
    "supportUrl": "supportURL",
    "privacyPolicyUrl": "privacyPolicyURL",
    "termsOfServiceUrl": "termsOfServiceURL",
}
# Docs: https://developers.openai.com/plugins/deploy/submission
_CODEX_MAX_CHARS = 30
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
# Folder entries the skills-only Codex directory rejects.
_CODEX_REJECTED = ("hooks", ".mcp.json", "commands", "rules")


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


def codex_errors(folder: Path, codex: dict) -> list[str]:
    """Return the Codex directory rules that the launcher package breaks."""
    errors = []
    iface = codex["interface"]
    for key in ("displayName", "shortDescription"):
        if len(iface[key]) > _CODEX_MAX_CHARS:
            errors.append(f"interface.{key} is longer than {_CODEX_MAX_CHARS} characters")
    if not _SEMVER.match(codex.get("version", "")):
        errors.append(f"version {codex.get('version')!r} is not semver")
    for key in ("logo", "composerIcon"):
        if not (folder / iface[key]).is_file():
            errors.append(f"interface.{key} file {iface[key]} does not exist")
    if not list((folder / "skills").glob("*/SKILL.md")):
        errors.append("skills/ has no <name>/SKILL.md")
    errors += [f"{name} is not allowed" for name in _CODEX_REJECTED if (folder / name).exists()]
    return [f"{folder.name}: {e}" for e in errors]


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
    manifests = launcher_manifests(plugin)
    errors = codex_errors(root / rel, manifests[".codex-plugin/plugin.json"])
    if errors:
        sys.exit("\n".join(f"ERROR: {e}" for e in errors))
    for name, data in manifests.items():
        out[f"{rel}/{name}"] = dumps(data)
    return out


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
    args = ap.parse_args()

    files = generate(ROOT)
    changed = [
        rel
        for rel, text in files.items()
        if not (ROOT / rel).exists() or (ROOT / rel).read_text() != text
    ]
    if args.check:
        sys.exit(report(changed))
    for rel in changed:
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[rel])
        print(f"  wrote {rel}")
    print(f"{len(files)} files, {len(changed)} changed.")


if __name__ == "__main__":
    main()
