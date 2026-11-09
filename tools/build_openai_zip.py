#!/usr/bin/env python3
"""Build one OpenAI plugin directory ZIP ("skills only") per public toolkit.

Usage: python tools/build_openai_zip.py [toolkit-name ...] [--logo PATH]

Writes dist/openai/<toolkit>-<version>.zip. Per toolkit the ZIP holds a Codex manifest
(.codex-plugin/plugin.json), skills/ (commands converted to skills) and other files; hooks,
local MCP config, rules and Claude-only files are dropped and listed. Exits non-zero when
something cannot be represented. --logo takes a square PNG used as composerIcon and logo
(OpenAI requires both; the repo ships none).

Docs: https://developers.openai.com/plugins/deploy/submission
      https://developers.openai.com/plugins/guides/submit-claude-plugin
"""

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "workbench"
OUT = ROOT / "dist" / "openai"

# the toolkits published to the OpenAI directory, with the listing text (limits: displayName and
# shortDescription 30 chars)
TOOLKITS = {
    "init": ("dltHub Init", "dltHub setup and secrets"),
    "quick-start": ("dltHub Quick Start", "From ingestion to dashboard"),
    "rest-api-pipeline": ("dltHub REST API Pipeline", "Build dlt REST API pipelines"),
    "sql-database-pipeline": ("dltHub SQL Database", "Load SQL databases with dlt"),
    "filesystem-pipeline": ("dltHub Filesystem Pipeline", "Load files with dlt"),
    "data-exploration": ("dltHub Data Exploration", "Profile data, build dashboards"),
    "transformations": ("dltHub Transformations", "Model data with dlt"),
    "data-quality": ("dltHub Data Quality", "Checks and metrics for dlt"),
    "dlthub-platform": ("dltHub Platform", "Deploy and debug on dltHub"),
    "performance": ("dltHub Performance", "Tune slow dlt pipelines"),
}
CATEGORY = "Developer Tools"  # docs: "a dashboard category title", list not published
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
# top-level names never shipped: hooks and local MCP are rejected, the rest is Claude/dlt specific
DROP = {
    "hooks": "lifecycle hooks are not accepted",
    ".mcp.json": "local (stdio) MCP is not accepted, only remote HTTPS MCP",
    ".claude-plugin": "replaced by .codex-plugin/plugin.json",
    ".claudeignore": "Claude-only",
    "rules": "OpenAI plugins have no rules concept",
    "CLAUDE.md": "Claude-only",
    "settings.json": "Claude-only",
    ".claude": "Claude-only",
}
SKIP_NAMES = {"__pycache__", ".DS_Store"}


def build(name: str, logo: Path | None) -> tuple[Path, list[str]]:
    src = SRC / name
    meta = json.loads((src / ".claude-plugin" / "plugin.json").read_text())
    version = meta.get("version", "")
    if not SEMVER.match(version):
        raise SystemExit(f"{name}: version {version!r} is not semver")
    if not meta.get("description"):
        raise SystemExit(f"{name}: plugin.json has no description")
    author = meta.get("author", {}).get("name")
    if not author:
        raise SystemExit(f"{name}: plugin.json has no author.name")
    display, short = TOOLKITS[name]
    if len(display) > 30 or len(short) > 30:
        raise SystemExit(f"{name}: displayName/shortDescription exceed 30 chars")
    if not list((src / "skills").glob("*/SKILL.md")):
        raise SystemExit(f"{name}: no skills/<name>/SKILL.md")
    for key in ("hooks", "commands", "agents", "userConfig"):
        if key in meta:
            raise SystemExit(f"{name}: plugin.json declares '{key}', convert by hand")

    files: dict[str, Path | bytes] = {}
    dropped: list[str] = []
    for srv, conf in meta.get("mcpServers", {}).items():
        if "command" not in conf:  # remote MCP is not allowed in skills-only plugins either
            raise SystemExit(
                f"{name}: mcpServers.{srv} is not a local stdio server, convert by hand"
            )
        dropped.append(f"plugin.json mcpServers.{srv} (local stdio MCP is not accepted)")
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if path.is_dir() or SKIP_NAMES & set(rel.parts):
            continue
        top = rel.parts[0]
        if top == "commands":
            continue  # converted below
        if top in DROP:
            if rel.as_posix() != ".claude-plugin/plugin.json":  # the manifest is converted
                dropped.append(f"{rel} ({DROP[top]})")
        elif rel.name == "hooks.json":
            dropped.append(f"{rel} (lifecycle hooks are not accepted)")
        else:
            files[rel.as_posix()] = path
    # commands become skills: commands/<n>.md -> skills/<n>/SKILL.md (same frontmatter)
    for cmd in sorted(src.glob("commands/*.md")):
        target = f"skills/{cmd.stem}/SKILL.md"
        if target in files:
            raise SystemExit(f"{name}: command '{cmd.stem}' collides with an existing skill")
        files[target] = cmd
        dropped.append(f"commands/{cmd.name} (converted to {target})")
    # dlthub/agents/* are dlt agent specs, not Claude subagents: shipped as plain files
    if any(k.startswith(("agents/", "hooks/")) for k in files):
        raise SystemExit(f"{name}: agents/ or hooks/ left in package")

    iface = {
        "displayName": display,
        "shortDescription": short,
        "longDescription": meta["description"],
        "developerName": author,
        "category": CATEGORY,
        "capabilities": [],
    }
    if logo:
        files["assets/logo.png"] = logo
        iface["composerIcon"] = iface["logo"] = "./assets/logo.png"
    else:
        dropped.append("WARNING no --logo: interface.composerIcon/logo missing (required by Codex)")
    manifest = {
        "name": name,
        "version": version,
        "description": meta["description"],
        "author": meta["author"],
        **{k: meta[k] for k in ("homepage", "repository", "license", "keywords") if k in meta},
        "skills": "./skills/",
        "interface": iface,
    }
    files[".codex-plugin/plugin.json"] = (json.dumps(manifest, indent=2) + "\n").encode()

    OUT.mkdir(parents=True, exist_ok=True)
    zip_path = OUT / f"{name}-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, content in sorted(files.items()):
            if isinstance(content, bytes):
                z.writestr(arc, content)
            else:
                z.write(content, arc)
    return zip_path, dropped


def main() -> int:
    args = sys.argv[1:]
    logo = None
    if "--logo" in args:
        i = args.index("--logo")
        logo = Path(args[i + 1]).resolve()
        del args[i : i + 2]
        if not logo.is_file():
            raise SystemExit(f"logo not found: {logo}")
    unknown = [n for n in args if n not in TOOLKITS]
    if unknown:
        raise SystemExit(f"not public toolkits: {unknown}")
    if OUT.exists() and not args:
        shutil.rmtree(OUT)
    for name in args or TOOLKITS:
        zip_path, dropped = build(name, logo)
        print(f"{name}: {zip_path.relative_to(ROOT)}")
        for d in dropped:
            print(f"    dropped: {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
