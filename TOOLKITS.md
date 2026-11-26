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
  "repository": "https://github.com/dlt-hub/dlthub-ai-harness",
  "license": "https://github.com/dlt-hub/dlthub-ai-harness/blob/master/LICENSE",
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
  "dependencies": ["init", "local-workspace"],
  "workflow_entry_skill": "setup-runtime",
  "agents": {"exclude": ["cortex"]},
  "components": {"skills/setup-runtime": {"agents": {"include": ["claude"]}}},
  "mcp_features": {"dlt-workspace-mcp": ["dlthub.jobs", "dlthub.logs"]}
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `listed` | `true` | When `false`, toolkit is hidden from `toolkit list` and `list_toolkits` MCP tool but can still be installed by name |
| `dependencies` | `[]` | Toolkits that are auto-installed before this one |
| `workflow_entry_skill` | — | Name of the skill where the workflow starts. Shown after install and in `dlthub ai status` |
| `agents` | all | The agents that see the toolkit: `{"include": [...]}` or `{"exclude": [...]}`, with names from `claude`, `cursor`, `codex`, `cortex`. Another agent does not see it in `toolkit list` and cannot install it without `--see-all` |
| `components` | — | The same visibility for one skill, command, rule, agent definition or MCP server, keyed `skills/<name>`, `commands/<name>`, `rules/<name>`, `dlthub/agents/<name>` or `mcp/<server>` |
| `mcp_features` | — | Feature groups the toolkit adds to the `--features` argument of an MCP server of another toolkit, keyed by server name. dlt keeps features the user already set, and warns when the server is not installed |

`agents`, `components` and `mcp_features` need dlt 1.33 or later.

## Platform toolkits

A **platform toolkit** deploys and runs a workspace on one platform: `dlthub-platform` for the dltHub platform, `snowflake-platform` for Snowflake. Platform toolkits are pluggable, so every other toolkit is agnostic to them:

- **The label.** A platform toolkit starts its description with `Platform toolkit (<platform>):`, in both `plugin.json` and `marketplace.json`. `dlthub ai toolkit list` shows it, so an agent can tell which toolkits deploy and where. The label is reserved for platform toolkits.
- **Toolkits that require a platform.** A toolkit that works only with one platform but is not its platform toolkit (`one-shot` and `dlthub-init-skills`, guided first deploys to the dltHub platform) ends its description with `Requires <platform> Platform.`, for example `Requires dltHub Platform.`. It may name its platform, like a platform toolkit, and the router and the generic toolkits do not name it.
- **Visibility.** A platform toolkit, and a toolkit that requires a platform, names the agents it is made for in `agents` (`snowflake-platform` is for Cortex Code, the dltHub ones are for every other agent). Its MCP tools come through `mcp_features` on `dlt-workspace-mcp`, never a second server.
- **Dependencies point one way.** A platform toolkit depends on `init` and `local-workspace` (jobs, deployments, local debug runs, the `prod` profile), and on the destination toolkit of its platform when there is one (`snowflake-platform` → `destination-snowflake`). It may name the generic toolkits in its handovers. No other toolkit depends on a platform toolkit.
- **One entry for every platform.** Each platform toolkit starts at `prepare-deployment` (local-workspace): it checks that the workspace is ready for a deployment and sends missing jobs, triggers and local runs to `define-and-debug-jobs`. A platform toolkit adds only what is its own (login, connection, its data connection, deploy, operations) and never repeats a local-workspace check.
- **Generic toolkits name no platform.** They never name a platform toolkit, a toolkit that requires a platform, or their skills, never say "dltHub platform" or "runtime", never run platform commands (`dlthub deploy`, `dlthub job`) and never install `dlt[hub]` or `dlthub-client`. An installed platform toolkit's own rule takes deploy intents, and `dlthub-router` installs one when none is, so their workflows list no platform handover; their skills say "follow the workflow entry of the installed platform toolkit" and write commands that every platform has without a prefix: `deploy`, `job run`, `job logs`.
- **Routing.** The `dlthub-router` index has one row for all of them: "deploy, schedule or run jobs on a platform → a platform toolkit". The agent picks one from `dlthub ai toolkit list` by the platform the user names. Once installed, a platform toolkit's rule says that it is the platform toolkit of the workspace, takes deploy intents, and maps the commands that other toolkits write without a prefix (`deploy`, `job run`, `job logs`) to its own CLI.

`make validate-toolkits` checks the label, `Requires <platform> Platform`, the router row and that the generic toolkits stay agnostic.

## Destination toolkits

A **destination toolkit** carries what one destination needs, beyond what dlt does for every destination: the connection, loading into it, and the ecosystem around it, such as the business context the destination already has, the semantic layer, and the destination's own ways to build a model (for example dynamic tables on Snowflake). The first is `destination-snowflake`. Platform toolkits are about deployments, jobs and observability; destination toolkits are about the destination and its data:

- **The label.** A destination toolkit starts its description with `Destination toolkit (<destination>):`, in both `plugin.json` and `marketplace.json`. The label is reserved for destination toolkits.
- **Visibility.** Every agent sees a destination toolkit. What only one agent can use is a component with its own `agents` in `components`: in `destination-snowflake`, the Cortex Code rule only for `cortex`, and the handover to Cortex Code (`use-cortex-code` rule, `delegate-to-cortex-code` skill) for every other agent.
- **Dependencies point one way.** A destination toolkit depends on `init`. Only a platform toolkit depends on a destination toolkit, its own destination's. A destination toolkit never depends on or names a platform toolkit: it hands jobs and deployment to "the installed platform toolkit".
- **Generic toolkits name no destination toolkit.** At each hook point they ask for "the destination toolkit" of the destination, and send a missing one to `dlthub-router`. The hook points: where a destination is chosen or configured (pipeline creation, `setup-secrets`, `setup-profiles`, the production destination in `prepare-deployment`), where a load fails on the destination (the debug skills), and where a model is built (`generate-cdm`, `create-transformation`, `incremental-transformation`), so that semantic layers and the destination's own tables plug into the transformations toolkit.
- **The destination toolkit's rule joins those steps.** Its workflow rule says, by step title and never by number, which steps of other toolkits it takes over or adds to, and that its skills win over the router for intents of its destination.
- **Routing.** The `dlthub-router` index has one row for all of them: "load into a named destination → a destination toolkit". The router description names each destination that has one (`Snowflake`), so it reacts when the user names it, and the `init` rule says that the router offers it. The agent picks the toolkit from `dlthub ai toolkit list` by the destination; it comes next to the workflow toolkit, which still owns the pipeline or the model.
- **Artifacts.** A destination toolkit writes next to the model, in `.dlthub/ontology/<name>/` (for example `snowflake_semantic_view.sql`, `snowflake_dynamic_tables.sql`). It has no folder of its own.

`make validate-toolkits` checks the label and its destination, the router row and description, and that only a platform toolkit depends on a destination toolkit and that no other toolkit names one.

## Artifact locations

Toolkits write their artifacts into a user's workspace only at these locations, all under `.dlthub/` and all committed. Rules compose: the `init` rule names the shared ones (`.dlthub/schemas/`, `.dlthub/ontology/<name>/`), the rule of the toolkit that owns a location names it (`.dlthub/explorations/` in data-exploration, `.dlthub/<platform>/` in each platform toolkit), and skills name every path they write. The [AI harness docs](https://dlthub.com/docs/hub/ai-harness/artifact-locations) list them all for the user.

| Location | What goes there | Who writes it | Git |
|---|---|---|---|
| `.dlthub/schemas/` | dlt schemas; the default `import_schema_path` | dlt, any toolkit | committed |
| `.dlthub/schemas/export/` | exported dlt schemas (`export_schema_path`), only when the user wants them committed | dlt | committed |
| `.dlthub/ontology/<name>/` | business knowledge and semantic information of one topic: `context.md`, annotated source DBML, `taxonomy.json`, `ontology.ison`, `ontology.md`, `CDM.dbml`, the semantic views and native tables of any destination | transformations, destination toolkits | committed |
| `.dlthub/explorations/<name>/` | data exploration plans | data-exploration | committed |
| `.dlthub/<platform>/` | what one platform toolkit keeps, for example deploy records in `deploy/<environment>/` (`.dlthub/snowflake/`, `.dlthub/platform/`) | that platform toolkit only | committed |

Rules for skill authors:

- **Name the path.** A skill that writes or reads an artifact names its location explicitly.
- **A new kind of artifact gets a location here first.** Do not invent a folder in a skill.
- **`<name>` in `.dlthub/ontology/<name>/` is chosen once** (`annotate-sources`, or the business context that a destination toolkit collects), and every other skill reads it from the folder.
- **Code layout is the user's.** Never prescribe where sources, pipelines or transformations live. A concrete code path is an example ("for example `pipelines/orders.py`"), or the skill asks the user. When a CLI writes a file somewhere (`dlthub pipeline init` writes to the project root), say so, and that the user may move it. transformations keeps `transformations/` as its default folder.
- **Throwaway scripts go to the system temp dir**, never into the workspace.
- **No `build/` folder.** The workspace `.gitignore` ignores every folder named `build/`.

`make validate-toolkits` checks that toolkit files name only these artifact locations, that a platform folder appears only in its own toolkit, and that no retired path remains (`.schema/`, `schemas/import`, `schemas/export`, `.dlthub/ontology/snowflake`, `tools/get_`).

## CLI commands

```
dlthub ai status
dlthub ai toolkit list                            [--see-all] [--location] [--branch]
dlthub ai toolkit info <name>                     [--see-all] [--location] [--branch]
dlthub ai toolkit install <name> [--agent] [--see-all] [--overwrite] [--strict] [--location] [--branch]
dlthub ai init              [--agent] [--overwrite] [--location] [--branch]
```

| Command | Description |
|---------|-------------|
| `status` | Show current AI setup: dlthub version, detected agent, installed toolkits with entry skills |
| `list` | List available toolkits with name, description, and install status |
| `info <name>` | Show toolkit contents (skills, commands, rules, MCP servers) |
| `install <name>` | Install toolkit components into the current project |
| `init` | Install the `init` toolkit: rules, the secrets skill and the MCP server config |

`list` only shows toolkits with `"listed": true` (or absent, which defaults to true). Unlisted toolkits can still be installed by name. `list`, `info` and `install` show only what the agent sees (`agents`, `components`); `--see-all` shows and installs everything.

`--branch` does not work as of dlt 1.31.0. The sparse clone is a `--depth=1` of the default branch, so the named ref is never fetched and the checkout fails with `pathspec '<branch>' did not match any file(s)`. The failure handler then deletes `~/.dlt/repos/<repo>`, so the next install re-clones from scratch. To install a toolkit from a branch, clone it yourself and pass `--location`:

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
| agent | `dlthub/agents/<name>/` | Directory with `AGENT.md` + optional Python modules, copied as a tree. Needs dlt 1.30.1a1 or later: before that the installer read `agents/` and skipped the folder without saying so. dlt 1.31.0 added the `<toolkit>` segment to the install path, so two toolkits may ship an agent of the same name |
| mcp | `plugin.json`, `.mcp.json`, or `mcp.json` | MCP server definitions, merged into platform config |
| ignore | `.claudeignore` | Glob patterns for files that the AI does not read or index |

## Platform support

| Component | Claude Code | Cursor | Codex | Cortex Code |
|-----------|------------|--------|-------|-------------|
| skill | native | native | native | native |
| command | native | native | converted to skill | native |
| rule | native | native | converted to skill | written into `CORTEX.md` |
| agent | read by dlt | read by dlt | read by dlt | read by dlt |
| mcp | native (JSON) | native (JSON) | native (TOML) | native (JSON), project and user config |
| ignore | native | native | native | none |

## Install paths

| Component | Claude Code | Cursor | Codex | Cortex Code |
|-----------|------------|--------|-------|-------------|
| skill | `.claude/skills/<name>/` | `.cursor/skills/<name>/` | `.agents/skills/<name>/` | `.cortex/skills/<name>/` |
| command | `.claude/commands/<name>.md` | `.cursor/commands/<name>.md` | `.agents/skills/<name>/SKILL.md` | `.cortex/commands/<name>.md` |
| rule | `.claude/rules/<toolkit>-<name>.md` | `.cursor/rules/<toolkit>-<name>.mdc` | `.agents/skills/<toolkit>-<name>/SKILL.md` | `.cortex/rules/<toolkit>-<name>.md`, all rules in the `# dltHub rules` section of `CORTEX.md` |
| agent | `.claude/dlthub/agents/<toolkit>/<name>/` | `.cursor/dlthub/agents/<toolkit>/<name>/` | `.agents/dlthub/agents/<toolkit>/<name>/` | `.cortex/dlthub/agents/<toolkit>/<name>/` |
| mcp | `.mcp.json` → `mcpServers` | `.cursor/mcp.json` → `mcpServers` | `.codex/config.toml` → `mcp_servers` | `.cortex/mcp.json` (Desktop) and `$SNOWFLAKE_HOME/cortex/mcp.json` (CLI) → `mcpServers` |
| ignore | `.claudeignore` | `.cursorignore` | `.codexignore` | — |

## Transforms applied during install

| Component | Claude Code | Cursor | Codex |
|-----------|------------|--------|-------|
| skill | passthrough | passthrough | passthrough |
| command | passthrough | passthrough | wrapped with `name`/`description` frontmatter |
| rule | non-Claude frontmatter stripped (keeps `name`, `description`) | `alwaysApply: true` added, `description` derived from first heading if missing | wrapped with `name`/`description` frontmatter |
| agent | passthrough (dlt reads it, not the host; see [create-background-agent](workbench/dlthub-platform/skills/create-background-agent/SKILL.md)) | passthrough | passthrough |
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
  workflow_entry_skill: find-sql-database-source
  files:
    .claude/rules/sql-database-pipeline-workflow.md:
      sha3_256: "abc123..."
  mcp_servers:
    - dlt-workspace-mcp
```

The CLI uses this file to compare versions on the next install, to show entry skills in `dlthub ai status` and to check file hashes (SHA3-256).

## Auto-detection priority

When `--agent` is omitted, the platform is detected in this order:

1. **Runtime env vars** (set by the IDE when it spawns the CLI): Claude Code > Codex > Cursor; Cortex Code by `CORTEX_CODE_CLIENT_SURFACE`
2. **Project-local file probes** (checked in priority order):
   - Claude Code: `.claude/`, `CLAUDE.md`
   - Codex: `.agents/`, `AGENTS.md`
   - Cursor: `.cursor/`, `.cursorignore`, `.cursorrules`
   - Cortex Code: `.cortex/`, `CORTEX.md`, `.snowflake/cortex/`
3. **Global (home dir) probes**: `~/.claude/`, `~/.codex/`, `~/.cursor/`, `$SNOWFLAKE_HOME/cortex/`

## MCP server sources

MCP server definitions are read from (in priority order):
1. `mcpServers` field in `.claude-plugin/plugin.json`
2. `.mcp.json` (Claude wrapper format: `{"mcpServers": {...}}`)
3. `mcp.json` (direct server dict)
