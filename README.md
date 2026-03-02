# dltHub AI Workbench

AI-assisted data engineering with [dlt](https://dlthub.com). Give your coding agent the skills to build, debug, and explore data pipelines.

Works with **Claude Code**, **Cursor**, and **Codex**.

## How to get started

### Via Anthropic plugin (cold start)

If you don't have dlt or Python set up yet:

1. Add the marketplace in Claude Code: `https://github.com/dlt-hub/dlthub-ai-workbench`
!- ADD EXACT CLAUDE CODE COMMAND HERE

2. Install the bootstrap toolkit:
   ```
   claude plugin install bootstrap@dlthub-ai-workbench --scope project
   ```
3. Run `/init-workspace` — it installs `uv`, creates a Python venv, installs `dlt`, and sets up AI agent support with `dlt ai init`.

### Via `dlt` (existing project)

If you already have a Python project:

```bash
uv pip install --upgrade dlt[workspace]==1.23.0a2
dlt ai init
```

`dlt ai init` auto-detects your coding agent (Claude Code, Cursor, or Codex) and installs shared rules, secrets handling, and the workspace MCP server.

Then install your first toolkit:

```bash
dlt ai toolkit list                           # see what's available
dlt ai toolkit rest-api-pipeline install      # install one
```

### Codex setup
Codex does not support commands and rules so we convert those into skills. Codex runs in pretty strict sandbox mode. You should consider giving access
to fetch web pages in your project or global config ie.
`.codex/config.toml`
```toml
web_search = "live"
```


## What is workbench

Workbench is a catalog of **toolkits** that teach AI coding agents how to work with [dlt](https://dlthub.com). It is backward compatible with the Anthropic (and Cursor) marketplace and plugin system.

Each toolkit is an ordered group of **skills**, **commands**, **rules**, and **MCP servers**. A **workflow** rule ties them together into a guided sequence — the agent knows which skill to use at each step.

```mermaid
graph TB
    subgraph Agent["AI Coding Agent"]
        A["Claude Code / Cursor / Codex"]
    end

    subgraph WB["Workbench — toolkits"]
        direction TB
        T2["<b>rest-api-pipeline</b><br/>Build, debug &amp; validate pipelines"]
        T4["<b>dlthub-runtime</b><br/>Deploy to dltHub platform"]
        T3["<b>data-exploration</b><br/>Query data &amp; build reports"]
        T1["<b>bootstrap</b><br/>Environment setup"]
        INIT["<b>init</b><br/>Shared rules, secrets &amp; MCP"]
    end

    subgraph Components["Toolkit anatomy"]
        direction LR
        SK["Skills<br/><i>step-by-step procedures</i>"]
        CMD["Commands<br/><i>slash commands</i>"]
        RU["Rules<br/><i>always-on context</i>"]
        MC["MCP servers<br/><i>data tools</i>"]
    end

    subgraph DLT["dlt runtime"]
        MCP["MCP Server"]
        CLI["dlt CLI"]
        PIPE["Pipelines &amp; Destinations"]
    end

    A -- invokes --> WB
    WB -. made of .-> Components
    A <-. tools .-> MCP
    MCP --> PIPE
    CLI --> PIPE
```

### Toolkits

| Toolkit | Description | Components |
|---------|-------------|------------|
| **rest-api-pipeline** | End-to-end REST API ingestion | 8 skills, workflow, MCP |
| **dlthub-runtime** | Deploy pipelines to dltHub platform | 4 skills, workflow, rules |
| **data-exploration** | Interactive data analysis and reporting | 2 skills |
| **bootstrap** | Cold-start environment setup | 1 command |
| **init** | Shared rules, secrets handling, workspace MCP | installed by `dlt ai init` |

### rest-api-pipeline workflow

Each toolkit workflow has an **entry skill** where it MUST start. The entry skill can be triggered explicitly (`/find-source`) or by low-intent user messages matching the skill description (e.g. "I want to load data from Stripe").

| Step | Skill | What it does |
|------|-------|-------------|
| **entry** | `find-source` | **Start here.** Discover a dlt source for your API |
| 1 | `create-rest-api-pipeline` | Scaffold pipeline code and configure credentials |
| 2 | `debug-pipeline` | Run, inspect traces and load packages, fix errors |
| 3 | `validate-data` | Check schema and data, fix types and structures |
| 4+ | `adjust-endpoint`, `new-endpoint`, `view-data` | Extend: pagination, incremental loading, more endpoints, data queries |

When the user's needs go beyond the toolkit, the workflow hands over to **data-exploration** or **dlthub-runtime**.

### data-exploration skills (WIP!)

| Skill | What it does |
|-------|-------------|
| `explore-data` | Query loaded data with the dlt dataset API and ibis |
| `create-marimo-report` | Build interactive marimo notebooks with charts and filters |

## How to use

### Option A: `dlt ai` command line

The `dlt ai` CLI manages toolkits and agent configuration. It auto-detects your coding agent and installs components in the right format.
When you use this option, toolkits become part of your workspace so **you can customize and hack them**. This follows the same philosophy
as our verified sources.

```bash
dlt ai status                                  # show AI setup status: version, agent, toolkits
dlt ai init                                    # set up agent support
dlt ai toolkit list                            # list available toolkits
dlt ai toolkit <name> info                     # show toolkit contents
dlt ai toolkit <name> install [--agent] [--overwrite]
dlt ai secrets list                            # show secret file locations
dlt ai secrets view-redacted [--path <file>]   # print secrets with values masked
dlt ai secrets update-fragment --path <file> '<toml>'  # merge TOML into secrets file
dlt ai mcp run [--stdio | --sse] [--features ...]
dlt ai mcp install [--agent] [--features ...] [--name]
```

#### Agent auto-detection

`dlt ai init` and `dlt ai toolkit install` auto-detect your coding agent from environment variables, project files, and global config directories. If exactly one agent is detected, it's used automatically. If multiple are found, you'll be asked to pass `--agent` explicitly.

#### Install paths

| | Claude Code | Cursor | Codex |
|---|---|---|---|
| Skills | `.claude/skills/` | `.cursor/skills/` | `.agents/skills/` |
| Commands | `.claude/commands/` | `.cursor/commands/` | converted to skills |
| Rules | `.claude/rules/` | `.cursor/rules/` | converted to skills |
| MCP | `.mcp.json` | `.cursor/mcp.json` | `.codex/config.toml` |

### Option B: Anthropic marketplace and plugins

Workbench toolkits are standard Claude Code plugins. You can browse and install them directly from the Anthropic marketplace in Claude Code — no `dlt` CLI needed.

1. Add the marketplace: `https://github.com/dlt-hub/dlthub-ai-workbench`
2. Boostrap `dlthub` Workspace. Use `dlt ai init` to get workspace rules.
3. Browse and install toolkits as plugins
4. Skills and commands appear in your agent immediately

This is the easiest path for Claude Code users who want to get started without touching the terminal.

### MCP server

Toolkits use the **dlt MCP server** for data access, secrets management, and workspace inspection — installed automatically with each toolkit.

Built-in features: `workspace` (pipeline discovery, workspace info), `pipeline` (table inspection, SQL queries, schema), `secrets` (list, view-redacted, update), `toolkit` (list, info). External packages can add more via `plug_mcp` hookimpls.

## Add and maintain Toolkits
See [CLAUDE](CLAUDE.md)

## License

[Elastic License 2.0](LICENSE) — use, modify, and distribute freely. Cannot be offered as a hosted/managed service.
