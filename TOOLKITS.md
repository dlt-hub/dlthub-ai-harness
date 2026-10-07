# Toolkits

How the dltHub AI Harness organizes toolkits and how `dlthub ai toolkit` installs them across AI platforms.

## Repository structure

```
.claude-plugin/
  marketplace.json          # registry of all plugins (for Claude marketplace)
workbench/
  init/                     # shared foundation toolkit
    .claude-plugin/
      plugin.json           # Claude plugin manifest (strict schema)
    rules/
    .mcp.json
    .claudeignore
  rest-api-pipeline/        # feature toolkit (depends on init)
  sql-database-pipeline/    # feature toolkit (depends on init)
    .claude-plugin/
      plugin.json           # Claude plugin manifest
      toolkit.json          # dlthub-specific metadata (dependencies, listed)
    skills/
      skill-name/
        SKILL.md
    commands/
      command-name.md
    rules/
      rule-name.md
    mcp.json
    .claudeignore
  bootstrap/                # unlisted toolkit
    .claude-plugin/
      plugin.json
      toolkit.json          # {"dependencies": ["init"], "listed": false}
    commands/
      init-workspace.md
```

## plugin.json

Each toolkit has `.claude-plugin/plugin.json` — the Claude plugin manifest with a **strict schema** (unrecognized keys cause validation errors). Only official Claude fields are allowed:

```json
{
  "name": "rest-api-pipeline",
  "description": "Build REST API pipelines with dlt: scope, debug and validate data",
  "version": "0.1.1",
  "author": {"name": "dlthub"},
  "homepage": "https://dlthub.com/docs",
  "repository": "https://github.com/dlt-hub/dlthub-ai-workbench",
  "license": "https://github.com/dlt-hub/dlthub-ai-workbench/blob/master/LICENSE",
  "keywords": ["dlthub", "etl", "data-pipeline"],
  "mcpServers": {
    "dlt-workspace-mcp": {
      "command": "uv",
      "args": ["run", "dlthub", "ai", "mcp", "--stdio"]
    }
  }
}
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | dir name | Display name used by CLI and MCP tools |
| `description` | yes | `""` | One-line description shown in `toolkit list` |
| `version` | yes | `""` | Semver string for install/upgrade tracking |
| `mcpServers` | no | — | MCP server definitions (alternative: standalone `.mcp.json` or `mcp.json`) |

Other Claude-valid fields (`author`, `homepage`, `repository`, `license`, `keywords`, `skills`, `commands`, `hooks`, `agents`, `outputStyles`, `lspServers`) are accepted by Claude but ignored by the dlthub CLI.

## toolkit.json

dlthub-specific metadata goes in `.claude-plugin/toolkit.json` alongside `plugin.json`. This file is optional and read only by the dlthub CLI — Claude ignores it. Its keys are merged on top of `plugin.json` values.

```json
{
  "dependencies": ["init"],
  "workflow_entry_skill": "find-source",
  "listed": false
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `listed` | `true` | When `false`, toolkit is hidden from `toolkit list` and `list_toolkits` MCP tool but can still be installed by name |
| `dependencies` | `[]` | Toolkits that are auto-installed before this one |
| `workflow_entry_skill` | — | Name of the skill where the workflow starts. Shown after install and in `dlthub ai status` |

## CLI commands

```
dlthub ai status
dlthub ai toolkit list                            [--location] [--branch]
dlthub ai toolkit info <name>                     [--location] [--branch]
dlthub ai toolkit install <name> [--agent] [--overwrite] [--strict] [--location] [--branch]
dlthub ai init              [--agent] [--overwrite] [--location] [--branch]
```

| Command | Description |
|---------|-------------|
| `status` | Show current AI setup: dlthub version, detected agent, installed toolkits with entry skills |
| `list` | List available toolkits with name, description, and install status |
| `info <name>` | Show toolkit contents (skills, commands, rules, MCP servers) |
| `install <name>` | Install toolkit components into the current project |
| `init` | Install the `init` toolkit: rules, the secrets skill and the MCP server config |

`list` only shows toolkits with `"listed": true` (or absent, which defaults to true). Unlisted toolkits can still be installed by name.

`--branch` does not work as of dlt 1.30.1a1. The sparse clone is a `--depth=1` of the default branch, so the named ref is never fetched and the checkout fails with `pathspec '<branch>' did not match any file(s)`. The failure handler then deletes `~/.dlt/repos/<repo>`, so the next install re-clones from scratch. To install a toolkit from a branch, clone it yourself and pass `--location`:

```bash
git clone --depth 1 --branch <branch> https://github.com/dlt-hub/dlthub-ai-harness.git /tmp/harness
```

```bash
dlthub --non-interactive ai toolkit install <name> --location /tmp/harness --overwrite
```

## MCP tools

When the `toolkit` feature is enabled, the dlthub MCP server exposes:

| Tool | Description |
|------|-------------|
| `list_toolkits` | Returns listed toolkit metadata (same filtering as `toolkit list`) |
| `toolkit_info` | Returns detailed toolkit contents by name |

## Component types

| Component | Source location | Description |
|-----------|----------------|-------------|
| skill | `skills/<name>/` | Directory with `SKILL.md` + supporting files, copied as a tree |
| command | `commands/<name>.md` | Single markdown file, slash-command or prompt template |
| rule | `rules/<name>.md` | Single markdown file, always-on context injected by the IDE |
| agent | `dlthub/agents/<name>/` | Directory with `AGENT.md` + optional Python modules, copied as a tree. Needs dlt 1.30.1a1 or later: before that the installer read `agents/` and skipped the folder without saying so. dlt 1.31.0 added the `<toolkit>` segment to the install path |
| mcp | `plugin.json`, `.mcp.json`, or `mcp.json` | MCP server definitions, merged into platform config |
| ignore | `.claudeignore` | Glob patterns for files that the AI does not read or index |

## Platform support

| Component | Claude Code | Cursor | Codex |
|-----------|------------|--------|-------|
| skill | native | native | native |
| command | native | native | converted to skill |
| rule | native | native | converted to skill |
| agent | read by dlt | read by dlt | read by dlt |
| mcp | native (JSON) | native (JSON) | native (TOML) |
| ignore | native | native | native |

## Install paths

| Component | Claude Code | Cursor | Codex |
|-----------|------------|--------|-------|
| skill | `.claude/skills/<name>/` | `.cursor/skills/<name>/` | `.agents/skills/<name>/` |
| command | `.claude/commands/<name>.md` | `.cursor/commands/<name>.md` | `.agents/skills/<name>/SKILL.md` |
| rule | `.claude/rules/<toolkit>-<name>.md` | `.cursor/rules/<toolkit>-<name>.mdc` | `.agents/skills/<toolkit>-<name>/SKILL.md` |
| agent | `.claude/dlthub/agents/<toolkit>/<name>/` | `.cursor/dlthub/agents/<toolkit>/<name>/` | `.agents/dlthub/agents/<toolkit>/<name>/` |
| mcp | `.mcp.json` → `mcpServers` | `.cursor/mcp.json` → `mcpServers` | `.codex/config.toml` → `mcp_servers` |
| ignore | `.claudeignore` | `.cursorignore` | `.codexignore` |

## Transforms applied during install

| Component | Claude Code | Cursor | Codex |
|-----------|------------|--------|-------|
| skill | passthrough | passthrough | passthrough |
| command | passthrough | passthrough | wrapped with `name`/`description` frontmatter |
| rule | non-Claude frontmatter stripped (keeps `name`, `description`) | `alwaysApply: true` added, `description` derived from first heading if missing | wrapped with `name`/`description` frontmatter |
| agent | passthrough (dlt reads it, not the host; see [create-background-agent](workbench/init/skills/create-background-agent/SKILL.md)) | passthrough | passthrough |
| mcp | passthrough (`type` field kept) | `type` field stripped | `type` field stripped, converted to TOML |
| ignore | passthrough (file renamed) | passthrough (file renamed) | passthrough (file renamed) |

## Dependencies and the `init` toolkit

The `init` toolkit contains shared rules, secrets handling, and the workspace MCP server. It is automatically installed (without overwrite) whenever any other toolkit is installed. It can also be installed explicitly via `dlthub ai init`.

Dependencies are declared in `toolkit.json` under `"dependencies"`. The CLI resolves them in topological order and installs any that are missing before installing the requested toolkit. Circular dependencies are detected and rejected.

## Install workflow

1. **Resolve agent** — use `--agent` or auto-detect (see below)
2. **Fetch the harness repo** — clone or update it in `~/.dlt/repos/`
3. **Install dependencies** — resolve dependency graph, install missing upstream toolkits
4. **Version check** — skip if same version already installed (unless `--overwrite`)
5. **Plan** — scan toolkit directory, build install actions, validate frontmatter
6. **Execute** — write files, merge MCP config, record in `.dlt/.toolkits` index

## Conflict handling

By default, when a destination path already exists, the CLI skips the component and logs a warning.

Pass `--overwrite` to `install` to replace existing files:
- Skills: merged into the existing folder. Files that the user added stay.
- Commands, rules, ignore files: overwritten.
- MCP servers: all servers from the toolkit are merged (existing entries with the same name are replaced)

Pass `--strict` to fail on validation warnings (for example, invalid frontmatter).

## Install tracking

Installed toolkits are recorded in `.dlt/.toolkits` (YAML):

```yaml
rest-api-pipeline:
  version: "0.1.1"
  installed_at: "2026-02-28T10:30:00+00:00"
  agent: claude
  description: "Build REST API pipelines with dlt: scope, debug and validate data"
  tags: [dlthub, etl, data-pipeline, python]
  workflow_entry_skill: find-source
  files:
    .claude/rules/rest-api-pipeline-workflow.md:
      sha3_256: "abc123..."
  mcp_servers:
    - dlt-workspace-mcp
sql-database-pipeline:
  version: "0.1.1"
  installed_at: "2026-02-28T10:30:00+00:00"
  agent: claude
  description: "Build SQL database pipelines with dlt"
  tags: [dlthub, sql, database, data-pipeline, python]
  workflow_entry_skill: find-source
  files:
    .claude/rules/sql-database-pipeline-workflow.md:
      sha3_256: "abc123..."
  mcp_servers:
    - dlt-workspace-mcp
```

The CLI uses this file to compare versions on the next install, to show entry skills in `dlthub ai status` and to check file hashes (SHA3-256).

## Auto-detection priority

When `--agent` is omitted, the platform is detected in this order:

1. **Runtime env vars** (set by the IDE when it spawns the CLI): Claude Code > Codex > Cursor
2. **Project-local file probes** (checked in priority order):
   - Claude Code: `.claude/`, `CLAUDE.md`
   - Codex: `.agents/`, `AGENTS.md`
   - Cursor: `.cursor/`, `.cursorignore`, `.cursorrules`
3. **Global (home dir) probes**: `~/.claude/`, `~/.codex/`, `~/.cursor/`

## MCP server sources

MCP server definitions are read from (in priority order):
1. `mcpServers` field in `.claude-plugin/plugin.json`
2. `.mcp.json` (Claude wrapper format: `{"mcpServers": {...}}`)
3. `mcp.json` (direct server dict)
