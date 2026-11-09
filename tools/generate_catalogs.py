#!/usr/bin/env python3
"""Generate the host catalogs and plugin manifests from the Claude ones, the single source of truth.

Source: .claude-plugin/marketplace.json and workbench/<toolkit>/.claude-plugin/plugin.json.

Usage: python tools/generate_catalogs.py [--check] [--public] [--no-hooks] [--out DIR]
  --check     write nothing, exit 1 if the files under --out differ from what would be generated
  --public    leave out bootstrap, one-shot and dlthub-init-skills (the Claude catalog keeps them)
  --no-hooks  omit hooks and MCP servers, for hosts that reject them
              (OpenAI directory, claude.ai chat)
  --out DIR   write under DIR instead of the repo root (the committed files are the default mode)

Formats, verified against the hosts' public docs on 2026-10-30:
- Cursor: https://cursor.com/docs/reference/plugins
  .cursor-plugin/marketplace.json (name, owner, plugins[{name, source, ...}], metadata) and
  <plugin>/.cursor-plugin/plugin.json. Cursor discovers skills/, rules/, commands/, agents/,
  hooks/hooks.json and mcp.json by default; `.mcp.json` needs an explicit "mcpServers" path.
- GitHub Copilot CLI: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference
  The catalog is searched at marketplace.json, .plugin/, .github/plugin/ (recommended) and
  .claude-plugin/ in that order, with the Claude format. A legacy plugin.json is also read from
  .claude-plugin/, so only the catalog at .github/plugin/marketplace.json is emitted.
  Also https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-marketplace
- Codex: https://developers.openai.com/codex/plugins/build (marketplace at
  .agents/plugins/marketplace.json, entries {name, source{source: local, path}, policy, category})
  and https://developers.openai.com/plugins/deploy/submission (.codex-plugin/plugin.json fields:
  skills, mcpServers as a path to ./.mcp.json, interface; hooks and local stdio MCP are rejected
  by the directory, hence --no-hooks).
- Gemini CLI: https://geminicli.com/docs/extensions/reference/
  gemini-extension.json must sit in the root of each extension. The docs describe no subdirectory
  install, so the per-toolkit file is at workbench/<toolkit>/gemini-extension.json and installs
  only via a local path or `gemini extensions link`, not from this repo's URL.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# not part of the public catalogs (Decision 2, issue #125)
NON_PUBLIC = {"bootstrap", "one-shot", "dlthub-init-skills"}
# fields copied from the Claude plugin.json into every host manifest
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
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def toolkit_manifests(tdir: Path, plugin: dict, hooks: bool) -> dict[str, dict]:
    """Per-toolkit manifests keyed by path relative to the toolkit directory."""
    meta = {k: plugin[k] for k in _META if k in plugin}
    mcp = hooks and (tdir / ".mcp.json").exists()
    hook_file = hooks and (tdir / "hooks" / "hooks.json").exists()

    cursor = dict(meta)
    codex = dict(meta)
    if (tdir / "skills").is_dir():
        codex["skills"] = "./skills/"
        # Codex `skills` accepts a path or an array of paths; codex/skills holds the rules skill
        if (tdir / "codex" / "skills").is_dir():
            codex["skills"] = ["./skills/", "./codex/skills/"]
    if hook_file:
        cursor["hooks"] = codex["hooks"] = "./hooks/hooks.json"
    if mcp:
        cursor["mcpServers"] = codex["mcpServers"] = "./.mcp.json"
    codex["interface"] = {
        "displayName": plugin["name"],
        "shortDescription": "dltHub toolkit",  # the directory caps it at 30 characters
        "longDescription": plugin["description"],
        "developerName": plugin.get("author", {}).get("name", ""),
        "category": "Data",
        "capabilities": [],
    }

    gemini = {k: plugin[k] for k in ("name", "version", "description")}
    # the intent index and rules of a toolkit live in AGENTS.md
    if (tdir / "AGENTS.md").exists():
        gemini["contextFileName"] = "AGENTS.md"
    if mcp:
        gemini["mcpServers"] = json.loads((tdir / ".mcp.json").read_text())["mcpServers"]

    return {
        ".cursor-plugin/plugin.json": cursor,
        ".codex-plugin/plugin.json": codex,
        "gemini-extension.json": gemini,
    }


def generate(root: Path, public: bool, hooks: bool) -> dict[str, str]:
    """Return {path relative to root: file text}."""
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
    entries = [p for p in market["plugins"] if not (public and p["name"] in NON_PUBLIC)]
    claude_format = dumps({**market, "plugins": entries})
    out = {
        # Copilot CLI and Cursor read the Claude catalog format as is
        ".github/plugin/marketplace.json": claude_format,
        ".cursor-plugin/marketplace.json": claude_format,
        ".agents/plugins/marketplace.json": dumps({
            "name": market["name"],
            "interface": {"displayName": market["name"]},
            "plugins": [
                {
                    "name": p["name"],
                    "source": {"source": "local", "path": p["source"]},
                    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    "category": p.get("category", "data").capitalize(),
                }
                for p in entries
            ],
        }),
    }

    for p in entries:
        rel = p["source"].removeprefix("./")
        tdir = root / rel
        plugin = json.loads((tdir / ".claude-plugin" / "plugin.json").read_text())
        for name, data in toolkit_manifests(tdir, plugin, hooks).items():
            out[f"{rel}/{name}"] = dumps(data)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--public", action="store_true")
    ap.add_argument("--no-hooks", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT)
    args = ap.parse_args()

    files = generate(ROOT, args.public, not args.no_hooks)
    changed = [
        rel
        for rel, text in files.items()
        if not (args.out / rel).exists() or (args.out / rel).read_text() != text
    ]
    if args.check:
        for rel in changed:
            print(f"  DIFF  {rel}")
        msg = (
            "Catalogs are up to date." if not changed else "Run: python tools/generate_catalogs.py"
        )
        print(msg)
        sys.exit(1 if changed else 0)
    for rel in changed:
        path = args.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[rel])
        print(f"  wrote {rel}")
    print(f"{len(files)} files, {len(changed)} changed.")


if __name__ == "__main__":
    main()
