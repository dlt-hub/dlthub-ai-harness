---
name: find-source
description: Find a dlt source for a given API or data provider. Use when the user asks about a source, wants to find a connector, or asks to implement a pipeline for a specific data source.
argument-hint: "[source-name] [context]"
---

# Find a dlt source

## Prerequisites
Skip this if you already checked it in this session.
1. Run `uv --version`. If it fails, `uv` is missing.
   - Ask the user to allow the `uv` install. Do not install it without approval.
   - On macOS and Linux, run `curl -LsSf https://astral.sh/uv/install.sh | sh`.
   - On Windows, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   - Docs: https://docs.astral.sh/uv/getting-started/installation/
   - If `uv` is still not found, tell the user to open a new shell, because the install changes `PATH`.
2. Run `uv run dlthub ai status`. If it fails, `dlt[hub]` or the dlthub workspace is missing.
3. Check that these skills are available. If a skill is not available, its toolkit is missing.
   - `setup-secrets` from the `init` toolkit
   - Do not check the `dlt-workspace-mcp` tools. They do not start without `dlt[hub]`.
4. Find how this skill was installed. Look at the folder of this skill.
   - The folder is in the project (`.claude/`, `.cursor/` or `.agents/`): the `dlthub` CLI installed it.
   - The folder is not in the project: a plugin marketplace installed it.
5. If anything is missing, tell the user that this skill does not work without it.
   - Ask the user to allow each install.
   - Install from the same channel as this skill. Then each toolkit has only one copy.
6. The `dlthub` CLI installed this skill:
   - If `dlt[hub]` or `init` is missing, run `uvx dlthub-init@latest`. It installs both.
   - For each other missing toolkit, run `uv run dlthub --non-interactive ai toolkit install <toolkit>`.
7. A plugin marketplace installed this skill:
   - If `dlt[hub]` or the workspace is missing, run `uvx --from "dlt[hub]" dlthub init`.
   - Do not run `uvx dlthub-init@latest`. It adds a second copy of `init`.
   - Ask the user to install each missing toolkit from the same marketplace.
   - In Claude Code, the command is `/plugin install <toolkit>@dlthub-ai-harness`.
8. After the install, tell the user to restart the session. Skills, rules and MCP load only at session start.
9. If the user refuses an install, stop. Do not run other steps of this skill.

Locate the best dlt source for what the user wants to extract data from.

Parse `$ARGUMENTS`:
- `source-name` (required): what the user wants to extract data from (e.g., "alpaca markets", "stripe", "postgres", "csv files", "rest api")
- everything after that: additional context, i.e. which data the user wants to ingest. In case the user does not specify, ask them which data they want to ingest.

## Steps

### 1. Classify the request

| User says (examples) | Core source |
|---|---|
| postgres, mysql, mssql, oracle, database, db, sql | `sql_database` |
| rest api, http api, web api, rest | `rest_api` |
| files, csv, parquet, jsonl, s3, gcs, azure blob, local files | `filesystem` |

If it matches a core source, skip to **step 5** and report the core source match.

### 2. Search verified sources

If the request looks like a specific API/service name, run:
```
dlthub --non-interactive pipeline init --list-sources
```
Search the output (case-insensitive) for the source name. If found, ensure that the verified source contains the data that the user needs (ask the user explicitly) skip to **step 5**

### 3. Search dlthub context

Use `search_dlthub_sources` mcp tool to look for sources. It is full-text search based so pass only essential keywords to it
ie. "claude analytics". You'll get description of the source and set of reference links to use in web search below.

### 4. Web search and validation

1. Confirm what you've found in **step 3** on the web. Extend the information on the endpoints and data they contains.
2. Perform additional web search to look for better alternatives.
3. **Avoid** 3rd party providers, integrators and proxies. Prefer **authoritative** answers ie.
```
query: <source-name> API documentation
```
4. Read **step 6** on what you will present to the user at the end.

NOTE: we can handle only REST API (**step 5**) and sometimes GraphQL.

### 5. Decide: is this a REST API pipeline?

This toolkit builds **REST API pipelines**. Before continuing, check if the user's data source actually fits.

**STOP and hand off** if any of these are true:
- **Core source is NOT `rest_api`** — the user needs `sql_database`, `filesystem`, or another core source. For `filesystem`, hand off to the **filesystem-pipeline** toolkit (`create-filesystem-pipeline`). For others, tell them which one and the `dlthub pipeline init` command, then suggest a general coding session.
- **A verified source exists** (from step 2) — a pre-built, maintained connector is almost always better than building from scratch. Tell the user about it and the `dlthub pipeline init <source> <destination>` command. Suggest they try the verified source first.

```
Found: <verified source or non-REST core source>
  Command: dlthub pipeline init <source> <destination>

This is outside the REST API pipeline workflow. You can:
  1. Use the verified source / core source above (recommended)
  2. Start a general coding session if you need a custom pipeline
```

**CONTINUE** only when the best path is building a REST API pipeline — either because:
- The user explicitly asked for REST API / HTTP API
- The data source is a REST API with no verified source available
- A dlthub context source was found (these use the `rest_api` core source under the hood)

### 6. Present findings
1. **high intent user** told you exactly what they want - exact API, endpoint or provider. If you have it - present the result. Only if not - alternatives
2. **low intent user** told you about the goals and why they need data. Allow them to make informed decision. Conversation will be needed!
3. Summarize
- Determine how many genuinely distinct options the user has.
A **viable option** is one that genuinely differs in tradeoffs — not every search result is a separate option. Only surface choices where the user's preference would actually matter (e.g. a paid source vs. a free public API they could hit directly). If one option is clearly best, just present that one.
- For each viable option, briefly describe what it provides, its init command, and what it requires (check the dlthub source page for requirements and use knowledge of the underlying API for its own access model).

### 7. Ask to pick single endpoint
Ask user to pick a single endpoint to start the work - do it directly or infer it from conversation.

Do NOT run `dlthub pipeline init` yet — wait for user confirmation.
After that continue workflow in `create-rest-api-pipeline` skill
