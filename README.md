# dltHub AI Workbench

**dlt** (data load tool) is an open-source Python library for loading data from APIs and databases into a warehouse or lakehouse. **dltHub** (paid platform) extends dlt with enterprise-grade features tailored to the needs of coding agents: transformations, data quality validation, managed runtime infrastructure, managed data apps, and an AI-powered workspace environment.

![AI Workbench Components](images/ai_workbench_components.png)

The **dltHub AI Workbench** is a collection of toolkits that give AI coding assistants step-by-step workflows to build data pipelines with dlt. You can use the workbench as-is or fork and customize it for your own stack. The **dlthub ai CLI** installs toolkit components into the right locations for your assistant and runs the workspace MCP server.

This is the **lean** workbench: it ships three ingestion toolkits — `rest-api-pipeline`, `sql-database-pipeline`, and `filesystem-pipeline` — covering OSS dlt (`dlthub.com/docs`). The premise is that a coding agent already knows how to write dlt pipelines; what it needs is *direction*. Each toolkit provides the sequence of steps, a doc link for the "how" of each step, and a verifiable check for when each step is done.

The dltHub AI Workbench is tested with **Claude Code**, **Cursor**, and **Codex** and may work with other AI coding assistants. We recommend workings in `accept edits` (Claude) / `--approval-mode` (Codex) mode to review the changes and familiarizing with dlthub AI workflows when getting started with the dlthub AI workbench.

## The dlthub AI workbench supports the iterative data engineering workflow

Building an ingestion pipeline is iterative, and each toolkit follows the same inner loop:

- Find or scaffold the source, then configure credentials
- Run on a sample and inspect the loaded tables before a full load
- Confirm the data looks right, then run the full load (adding incremental loading where the source supports it)
- Loop back to refine until the pipeline is solid

Every step points at an authoritative dlt doc for the "how", and closes with a verifiable "done when" check before the agent moves on.

![Data Development Lifecycle](images/data_development_lifecycle.png)

## dltHub AI Workbench Toolkits

The workbench gives your coding assistant **toolkits** — each a structured, guided workflow for one ingestion source type. Instead of generating ad-hoc code, the assistant follows a defined sequence of steps from start to finish.

The lean workbench is built from three kinds of content:

![AI Workbench](images/ai_workbench.png)

### The three layers

| Layer | What it is | When it runs |
|-------|-----------|-------------|
| **SOUL** | The agent's identity and guardrails, written as character (cwd grounding, secrets-as-sacred, sample-before-full-load, prefer dlt built-ins, docs-from-the-source) | Always loaded — shipped by the `init` base toolkit |
| **Routing index** | The intent → toolkit → parent skill table, with disambiguation notes | Always loaded — shipped by the `init` base toolkit |
| **Parent skill** | One per toolkit: the ordered sequence, a doc link per step, and a verifiable "done when" check | Loaded when the user's intent matches the toolkit |

The always-on content lives in the **`init`** base toolkit, a dependency of every workflow toolkit: `init/rules/SOUL.md` and `init/rules/toolkit-index.md` install as always-on rules (Claude/Cursor), and `init/AGENTS.md` inlines both for Codex (where rules are opt-in). Installing any toolkit pulls `init` in, so SOUL and routing are always present. Beyond `init`, a workflow toolkit is just its parent skill plus its plugin manifests — no sub-skills or workflow files.

### MCP tools

**dlt-workspace-mcp** (local, configured via each toolkit's `plugin.json`) gives the agent structured context so it never has to copy-paste output into chat. It exposes data inspection tools (`list_tables`, `preview_table`, `execute_sql_query`, `get_row_counts`, `display_schema`, `get_local_pipeline_state`) and secrets tools (`secrets_view_redacted`, `secrets_update_fragment`) for inspecting and updating credentials without reading raw values.

### Available toolkits

Each toolkit's parent skill is named the same as the toolkit; invoke it with `/<toolkit-name>` or just describe your intent.

| Toolkit | What it does | Example prompt |
|---------|--------------|----------------|
| `rest-api-pipeline` | Load data from a REST API or HTTP endpoint (Stripe, GitHub, Salesforce, HubSpot, any web service) | *"Load data from the Stripe API into DuckDB"* |
| `sql-database-pipeline` | Load tables from a SQL database (Postgres, MySQL, SQL Server, Snowflake, BigQuery) | *"Load tables from my Postgres database into DuckDB"* |
| `filesystem-pipeline` | Load files (CSV, Parquet, JSONL) from local disk, S3, GCS, Azure, or SFTP | *"Load my S3 CSV files into DuckDB"* |


## Getting started

### New project (recommended)

To set up a clean new dlthub project with AI support, run [`dlthub-init`](https://pypi.org/project/dlthub-init/). It is non-interactive and AI-aware, so **your coding assistant can run it for you** — this is the command an agent should use to set up a clean new dlthub project. It pins `dlt[hub]` via a bundled lock and runs `uv sync`:

```bash
uvx dlthub-init@latest <dir>    # scaffold a clean new project into <dir>
```

### Existing project

To add the AI workbench to an existing project, run the same [`dlthub-init`](https://pypi.org/project/dlthub-init/) **in place**. It uses per-file collision handling (merges `pyproject.toml`, never overwrites `secrets.toml`, unions `.gitignore`), pins `dlt[hub]`, and runs `uv sync` — and, being non-interactive, your coding assistant can run it for you:

```bash
uvx dlthub-init@latest          # set up AI support in the current directory
```

**Manual steps (fallback):** if you'd rather do it step by step, or `dlthub-init` isn't available:

> **Note:** All `dlthub ai` commands below use `uv run dlthub ...` syntax. If you have `dlthub` installed globally or in an active virtual environment, you can omit `uv run` and call `dlthub` directly. We recommend using uv.

```bash
# Initialize the environment 
uv init 

# Install dlthub
uv add "dlt[hub]"

# Initialize the dlthub workspace and follow its instructions (most importantly `uv sync`)
uv run dlthub init

# Set up AI support (auto-detects your coding assistant)
uv run dlthub ai init

# If multiple coding assistants are detected, specify one explicitly:
uv run dlthub ai init --agent <agent>  # <agent>: claude | cursor | codex
```


`dlthub ai init` detects your coding assistant from environment variables and config files, then installs skills, rules, and the MCP server in the correct locations for that tool.

> **Claude Code note:** Add the following to your `CLAUDE.md` to enforce safe credential handling:
> ```markdown
> CRITICAL: never ask for credentials in chat. Always let the user edit secrets directly and do not attempt to read them.
> ```

> **Cursor note:** After running the command, manually enable the dlt-workspace-mcp server in **Cursor Settings > MCP**. Add the following to your `.cursor/rules/security.mdc` to enforce safe credential handling:
> ```markdown
> CRITICAL: never ask for credentials in chat. Always let the user edit secrets directly and do not attempt to read them.
> ```

> **Codex note:** Codex does not support commands and rules, so the installer converts those into skills and AGENTS.md. Codex also runs in a strict sandbox — consider enabling web access in your project or global config:
> ```toml
> # .codex/config.toml
> web_search = "live"
> ```
> Add the following to your `AGENTS.md` to enforce safe credential handling:
> ```markdown
> CRITICAL: never ask for credentials in chat. Always let the user edit secrets directly and do not attempt to read them.
> ```

### First-time onboarding (want to try or learn dltHub)

New to dltHub and just want to try or learn it? Run [`dlthub-start`](https://pypi.org/project/dlthub-start/) **yourself** — it scaffolds a fresh **playground** workspace (not for production, not for setting up a real project):

```bash
uvx dlthub-start@latest
```

> **Run this yourself — don't ask your coding assistant.** `uvx dlthub-start` must be run by a human because it requires interaction for authentication; it only works in a real terminal (not `!` mode). For agent-driven setup, use [`dlthub-init`](#new-project-recommended) above.

### Browse and install toolkits

> **Don't have dlthub set up yet?** Follow [New project](#new-project-recommended) or [Existing project](#existing-project) above first. The toolkit commands below assume `dlthub` is installed in your environment.


```bash
uv run dlthub ai toolkit list
```

Install the ingestion toolkits (install all three, or just the one matching your source). The `init` base toolkit is pulled in automatically as a dependency, so SOUL and routing are always present:

```bash
uv run dlthub ai toolkit install rest-api-pipeline
uv run dlthub ai toolkit install sql-database-pipeline
uv run dlthub ai toolkit install filesystem-pipeline
```

### Starting the workbench

Use one of the example prompts from the [Available toolkits](#available-toolkits) table above to kick off a workflow.

**Claude Code** — start a new session via `claude` in your terminal. Restart after installation for skills and MCP to take effect.

**Cursor** — open the project in Cursor and use the chat panel (Cmd+L). The installed skills are picked up automatically.

**Codex** — launch the Codex CLI via `codex` or use the Codex chat in the UI. Restart Codex after setup for the MCP server to take effect.

### Claude Code marketplace plugin (Early Access)

> **Early Access:** The Claude Code plugin is currently in early access. If you're new to dltHub and want to try or learn it, see [First-time onboarding](#first-time-onboarding-want-to-try-or-learn-dlthub) — you run `uvx dlthub-start@latest` yourself. To set up a clean new or existing dlthub project for agent-driven work, use `uvx dlthub-init@latest` (see [New project](#new-project-recommended)).

The workbench is also available as a Claude Code plugin via the marketplace. Start a Claude Code session and run:

Install `init` first (it carries SOUL + routing and is a dependency of every toolkit), then the ingestion toolkits:

```
/plugin marketplace add dlt-hub/dlthub-ai-workbench
/plugin install init@dlthub-ai-workbench --scope project
/plugin install rest-api-pipeline@dlthub-ai-workbench --scope project
/plugin install sql-database-pipeline@dlthub-ai-workbench --scope project
/plugin install filesystem-pipeline@dlthub-ai-workbench --scope project
```

Start a new session — plugins take effect only after restarting Claude Code: `claude`

> **Resuming a session?** Plugins installed mid-session are not active until you start a new one.


## The `dlthub ai` CLI

The `dlthub ai` subcommand is the bridge between the workbench and your coding assistant. `dlthub ai init` installs project rules, a secrets management skill, appropriate ignore files, and configures the dlt MCP server for your agent. `dlthub ai toolkit install` copies additional toolkit components (skills, rules, commands) into the right locations for your assistant.

**Toolkit management** — copies skills, rules, commands, and MCP config from the workbench into your project's agent config directory (`.claude/`, `.cursor/`, `.agents/`, etc.):

```bash
uv run dlthub ai status                        # show installed agent, dlthub version, active toolkits
uv run dlthub ai toolkit list                  # list available toolkits from the workbench
uv run dlthub ai toolkit info <name>           # show a toolkit's skills, commands, and workflow
uv run dlthub ai toolkit install <name>        # install a toolkit for the detected agent
uv run dlthub ai toolkit install <name> --agent <agent>  # <agent>: claude | cursor | codex  - override agent detection
```

**Secrets management** — dlt stores credentials in TOML files; these commands let the assistant inspect and update them without reading raw secret values:

```bash
uv run dlthub ai secrets list                  # show which secret files exist and where
uv run dlthub ai secrets view-redacted         # print secrets with values masked
uv run dlthub ai secrets update-fragment --path <file> '<toml>'  # merge a TOML snippet into a secrets file
```

**MCP server** — starts a local server that exposes your dlthub workspace (pipelines, schemas, tables, secrets) as tools the assistant can call:

```bash
uv run dlthub ai mcp run                       # run in SSE mode (default)
uv run dlthub ai mcp run --stdio               # run in stdio mode (for assistants that require it)
uv run dlthub ai mcp install                   # register the MCP server in the agent's config
```

The MCP server allows the assistant to answer questions like "what tables were loaded?" or "show me the schema" without you having to copy-paste output into the chat.

## License

This project is licensed under the [dltHub AI Workbench License](LICENSE).
