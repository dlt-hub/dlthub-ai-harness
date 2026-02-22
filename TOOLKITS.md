# Component compatibility matrix

How `dlt ai toolkit` manages workbench components across AI platforms.

## CLI commands

```
dlt ai toolkit list                            [--location] [--branch]
dlt ai toolkit <name> info                     [--location] [--branch]
dlt ai toolkit <name> install [--agent] [--overwrite] [--location] [--branch]
```

| Command | Description |
|---------|-------------|
| `list` | List available toolkits with name and description |
| `<name> info` | Show what's inside a toolkit (skills, commands, rules, MCP servers) |
| `<name> install` | Install toolkit components into the current project |

## Component types

| Component | Source | Description |
|-----------|--------|-------------|
| skill | `skills/<name>/` | Directory with `SKILL.md` + supporting files, copied as a tree |
| command | `commands/<name>.md` | Single markdown file, slash-command or prompt template |
| rule | `rules/<name>.md` | Single markdown file, always-on context injected by the IDE |
| mcp | `mcp.json` | MCP server definitions, merged into platform config |
| ignore | `.claudeignore` | Glob patterns for files the AI should not read or index |

## Platform support

| Component | Claude Code | Cursor | Codex |
|-----------|------------|--------|-------|
| skill | native | native | native |
| command | native | native | converted to skill |
| rule | native | native | converted to skill |
| mcp | native (JSON) | native (JSON) | native (TOML) |
| ignore | native | native | native |

## Install paths

| Component | Claude Code | Cursor | Codex |
|-----------|------------|--------|-------|
| skill | `.claude/skills/<name>/` | `.cursor/skills/<name>/` | `.agents/skills/<name>/` |
| command | `.claude/commands/<name>.md` | `.cursor/commands/<name>.md` | `.agents/skills/<name>/SKILL.md` |
| rule | `.claude/rules/<plugin>-<name>.md` | `.cursor/rules/<plugin>-<name>.mdc` | `.agents/skills/<plugin>-<name>/SKILL.md` |
| mcp | `.mcp.json` → `mcpServers` | `.cursor/mcp.json` → `mcpServers` | `.codex/config.toml` → `mcp_servers` |
| ignore | `.claudeignore` | `.cursorignore` | `.codexignore` |

## Transforms applied during install

| Component | Claude Code | Cursor | Codex |
|-----------|------------|--------|-------|
| skill | passthrough | passthrough | passthrough |
| command | passthrough | passthrough | wrapped with `name`/`description` frontmatter |
| rule | non-Claude frontmatter stripped (keeps `name`, `description`) | `alwaysApply: true` added, `description` derived from first heading if missing | wrapped with `name`/`description` frontmatter |
| mcp | passthrough (`type` field kept) | `type` field stripped | `type` field stripped, converted to TOML |
| ignore | passthrough (file renamed) | passthrough (file renamed) | passthrough (file renamed) |

## `_init` toolkit

The `_init` toolkit contains shared rules and ignore patterns. It is automatically installed (without overwrite) whenever any toolkit is installed. It does not appear in `list` output and cannot be installed directly via `install` — use `dlt ai init` for explicit installation.

## Conflict handling

By default, when a destination path already exists the component is skipped with a warning.

Pass `--overwrite` to `install` to replace existing files:
- Skills: `shutil.copytree` with `dirs_exist_ok=True` (merges into existing directory, user files preserved)
- Commands, rules, ignore: `write_text` overwrites the file
- MCP servers: all servers from the toolkit are merged (existing entries with the same name are replaced)

## Auto-detection priority

When `--agent` is omitted, the platform is detected in this order:

1. **Runtime env vars** (set by the IDE when it spawns the CLI): Claude Code > Codex > Cursor
2. **Project-local file probes** (checked in priority order):
   - Claude Code: `.claude/`, `CLAUDE.md`
   - Codex: `.agents/`, `AGENTS.md`
   - Cursor: `.cursor/`, `.cursorignore`, `.cursorrules`
3. **Global (home dir) probes**: `~/.claude/`, `~/.codex/`, `~/.cursor/`
