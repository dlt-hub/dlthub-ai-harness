---
name: find-source
description: Find a dlt source for a given API or data provider. Use when the user asks about a source, wants to find a connector, or asks to implement a pipeline for a specific data source.
argument-hint: <source-name>
---

# Find a dlt source

Locate the best dlt source for what the user wants to extract data from.

Parse `$ARGUMENTS`:
- `source-name` (required): what the user wants to extract data from (e.g., "alpaca markets", "stripe", "postgres", "csv files", "rest api")

## Steps

### 1. Classify the request

Determine if the source name maps to a **built-in core source**:

| User says (examples) | Core source |
|---|---|
| postgres, mysql, mssql, oracle, database, db, sql | `sql_database` |
| rest api, http api, web api, rest | `rest_api` |
| files, csv, parquet, jsonl, s3, gcs, azure blob, local files | `filesystem` |

If it matches a core source, skip to **step 4** and report the core source match.

### 2. Search verified sources

If the request looks like a specific API/service name, run:
```
dlt init --list-sources
```
Search the output (case-insensitive) for the source name. If found, report the match and the `dlt init <source> <destination>` command. Done.

### 3. Search dlthub context

If not found in verified sources, use web search:
```
query: dlthub.com source <source-name>
```

Look for results matching `dlthub.com/workspace/source/<slug>` or `dlthub.com/context/source/<slug>`.

If a match is found, fetch the page to extract the exact `dlt init dlthub:<source_identifier> <destination>` command:
```
WebFetch: https://dlthub.com/workspace/source/<slug>
```

### 4. Validate and present

Before reporting, assess everything found and determine how many genuinely distinct options the user has.

**If the request maps to a core source (step 1):** report it directly — no confirmation needed.
```
Core source: <source_type>
  sql_database: extracts tables from SQL databases (Postgres, MySQL, MSSQL, Oracle, etc.)
  rest_api: declarative REST API connector with auth, pagination, and incremental loading
  filesystem: reads files (CSV, Parquet, JSONL) from local disk or cloud storage (S3, GCS, Azure)
```

**Otherwise:** for each viable option, briefly describe what it provides, its init command, and what it requires (check the dlthub source page for dlthub source requirements and use knowledge of the underlying API for its own access model).

A "viable option" is one that genuinely differs in tradeoffs — not every search result is a separate option. Only surface choices where the user's preference would actually matter (e.g. a paid dlthub source vs. a free public API they could hit directly). If one option is clearly best, just present that one.

Do NOT run `dlt init` yet — wait for user confirmation.

### 5. Web search fallback

If no match was found, or the match doesn't cover what the user actually needs — do a short web search to find the **primary API or data source** the user should be using:

```
query: <source-name> API documentation
```

Based on the search results, determine if a **core source type** fits as a fallback:

| Data source is... | Core source | Init command |
|---|---|---|
| A REST/HTTP API | `rest_api` | `dlt init rest_api duckdb` |
| A SQL database | `sql_database` | `dlt init sql_database duckdb` |
| Files (local/cloud) | `filesystem` | `dlt init filesystem duckdb` |

Prefer falling back to a core source when possible — it gives a proper template with full configuration examples (e.g., `RESTAPIConfig` with auth, pagination, incremental loading). Using an unknown source name with `dlt init <name> duckdb` gives a generic intro template that is much less useful.

Report to the user:
- What the actual API/service is (name, docs URL)
- Which core source type fits and why (or `dlt init <source-name> duckdb` if nothing fits)
- The `dlt init` command to run
- One sentence on what credentials are needed, and ask if they have access or need help
