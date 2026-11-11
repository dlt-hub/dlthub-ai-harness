---
name: find-source
description: Find a dlt source for a given API or data provider. Use when the user asks about a source, wants to find a connector, or asks to implement a pipeline for a specific data source.
argument-hint: "[source-name] [context]"
---

# Find a dlt source

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

### 5. Decide: REST API pipeline, verified source, or another toolkit?

This toolkit builds **REST API pipelines** and runs **verified sources**. Before continuing, check which one fits the user's data source.

**STOP and hand off** if the core source is NOT `rest_api`:
- `sql_database` → hand off to the **sql-database-pipeline** toolkit, entry skill `find-sql-database-source`. Pass on the database and the destination if they are known.
- `filesystem` → hand off to the **filesystem-pipeline** toolkit (`create-filesystem-pipeline`).
- Another core source → tell the user which one and the `dlthub pipeline init` command, then suggest a general coding session.

**A verified source exists** (from step 2): a pre-built, maintained connector is almost always better than building from scratch. Recommend it:

```
Found verified source: <source>
  Command: dlthub pipeline init <source> <destination>

You can:
  1. Use the verified source (recommended)
  2. Build a custom REST API pipeline instead
```

If the user picks the verified source, skip steps 6–7 and go to **step 8**.

**CONTINUE** with step 6 only when the best path is building a REST API pipeline — either because:
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

### 8. Verified source path

Only when the user picked a verified source in step 5. Do NOT use `create-rest-api-pipeline`:
1. **Confirm the destination**, then scaffold from the project root:
   ```
   uv run dlthub --non-interactive pipeline init <source> <destination>
   ```
   It copies the source code into `<source>/`, adds an example script `<source>_pipeline.py`, and writes config and secret placeholders. Install the dependencies it reports.
2. **Read `<source>/README.md`** and the docs page it links. In a versioned source, **Maintenance & Troubleshooting** (**Operations** in older versions) lists known limits, quirks and their workarounds, and the **Changelog** says what changed in each version.
3. **Trim `<source>_pipeline.py`** to the resources the user asked for. Do not edit the code in `<source>/`: local changes block later updates of the source.
4. **Credentials** → `setup-secrets`. Write placeholders only; the user fills in the values.
5. **Get feedback** on the files you changed, then run it with `debug-pipeline` (it has a section on verified sources), then `validate-data`.
