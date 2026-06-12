---
name: create-minimal-pipeline
description: Build and run a minimal REST API pipeline locally against DuckDB. Use when the user wants to build a dlt pipeline for an API, load data from an API endpoint into DuckDB, create a REST API pipeline, or names a REST API source and/or endpoint to connect to and load data from.
argument-hint: "[api-name] [endpoint-hint]"
---

Build a minimal single-endpoint pipeline and run it locally against DuckDB. The finish line is `dlthub local show` — the moment the user sees their loaded data in the local UI. Every feature beyond the minimum (pagination, incremental loading, multiple endpoints) increases run time and failure surface, delaying that moment.

**This skill is for REST API / HTTP API sources only.** If the user is asking about:
- A SQL database (Postgres, MySQL, BigQuery, etc.) → install the `sql-database-pipeline` toolkit
- Files or object storage (S3, GCS, CSV, Parquet, SFTP, etc.) → install the `filesystem-pipeline` toolkit

To install: `uv run dlthub --non-interactive ai toolkit install <toolkit-name>`

**This skill loads 50 rows only.** It is a first-run validation, not a production pipeline.

Only propose toolkit installation if the user explicitly asks for something this skill does not cover (full data load, pagination, incremental loading, schema hints, multiple endpoints). Do not proactively suggest installing toolkits — mention them only when directly asked.

**Reference**: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic

## Step 0 — No source named?

If the user hasn't named a specific API, suggest these three directly:

> Here are a few popular sources you can try:
> - `github` — issues, pull requests, repositories
> - `hubspot` — contacts, companies, deals, tickets
> - `stripe_analytics` — customers, subscriptions, events
>
> You can also name any REST API not in the list (e.g. Notion, Jira, Shopify) and I'll build a custom connector for it.

Wait for the user to pick or name one. Then check if an endpoint was mentioned in the original prompt — if not, ask which endpoint they'd like to load. Then continue to Step 1.

## Step 1 — Research the API

Check for a verified source first. Tell the user you're doing this because a pre-maintained dlt source — if one exists — which is more reliable than a custom connector:

```
uv run dlthub --non-interactive pipeline init --list-sources | grep -i <api-name>
```

If a match is found, tell the user: "A verified source exists for `<api-name>` — you can use `dlthub pipeline init <source> duckdb` for a maintained connector." Then proceed with the custom pipeline.

Use your web search tool directly — do not spawn subagents, research agents, or delegate this step. One or two inline searches is all that's needed.

Web search: `<api-name> REST API documentation` and `<api-name> REST API authentication`.

Extract:
- `base_url` — root URL shared by all endpoints (e.g. `https://api.github.com`)
- Auth method — Bearer token, API key (header or query param), HTTP Basic, or none
- One clear endpoint — if the user named one in their prompt, use it; otherwise pick the most useful starting resource (e.g. `/repos`, `/orders`, `/events`)
- Response wrapper key — does data sit under `"data"`, `"items"`, `"results"`, or is it a root array?

One or two targeted searches is enough. If auth docs are on a separate page, fetch it too.

## Step 2 — Write the pipeline file

Create `<source>_pipeline.py`. Follow the exact pattern from `pipeline.py`:

### Rules

- `destination="duckdb"` always — runs locally against DuckDB
- `.add_limit(50, count_rows=True)` always — row limit, not page limit; omitting `count_rows=True` silently loads the entire dataset when a paginator is active
- Omit `data_selector` if the response is a root JSON array; if the wrapper key is ambiguous or undocumented, omit it first and check the row count — dlt will raise a clear error if the selector is wrong
- Omit pagination config — `.add_limit(50, count_rows=True)` caps the run; let dlt auto-detect or stop naturally

```python
"""<Source> dlt pipeline.

Loads <endpoint> from the <Source> REST API into the duckdb.
"""

import dlt
from dlt.sources.rest_api import rest_api_source
from dlt.hub import run


def <source>():
    return rest_api_source(
        {
            "client": {
                "base_url": "<base_url>",
                # Add auth here if the API requires it — see auth patterns below
            },
            "resources": [
                {
                    "name": "<endpoint>",
                    "endpoint": {
                        "path": "<path>",
                        "data_selector": "<wrapper_key>",  # e.g. "data", "items" — omit if response is a root array
                    },
                    "primary_key": "id",  # adjust to the resource's actual unique key
                },
            ],
        }
    )


@run.pipeline("<source>_pipeline")
def load_<source>():
    """Load <endpoint> from <Source>."""

    pipeline = dlt.pipeline(
        pipeline_name="<source>_pipeline",
        destination="duckdb",
        dataset_name="<source>",
    )

    load_info = pipeline.run(<source>().add_limit(50, count_rows=True), write_disposition="replace")  # row limit, not page limit
    print(load_info)


if __name__ == "__main__":
    load_<source>()
```

If the API is public (no auth needed), skip auth entirely — omit the `"auth"` key from `"client"`.

### Auth patterns

Pick the one that matches the API. Add it under `"client"`:

```python
# Bearer token
"auth": {"type": "bearer", "token": dlt.secrets["sources.<source>.token"]}

# API key in header
"auth": {"type": "api_key", "name": "X-API-Key", "api_key": dlt.secrets["sources.<source>.api_key"], "location": "header"}

# API key in query param
"auth": {"type": "api_key", "name": "api_key", "api_key": dlt.secrets["sources.<source>.api_key"], "location": "query"}

# HTTP Basic
"auth": {"type": "http_basic", "username": dlt.secrets["sources.<source>.username"], "password": dlt.secrets["sources.<source>.password"]}
```

## Step 3 — Handle credentials

**Skip this step entirely if the API is public (no auth needed).**

Do not read or write `.dlt/secrets.toml` directly — use the MCP secrets tools.

**3a. Check what's already configured:**

Use `secrets_view_redacted` — if `[sources.<source>]` already has the required field populated (shown as `***`), skip to Step 4.

**3b. If the credential is missing**, use `secrets_update_fragment` with `path=".dlt/secrets.toml"` to write the credential skeleton with an empty placeholder value:

```toml
[sources.<source>]
token = ""
```

Use `secrets.toml` (workspace-scoped) so credentials are visible to all profiles — credentials in `dev.secrets.toml` are not visible to the platform's prod profile and the job will fail.

Then tell the user:

> I've added the credential structure to `.dlt/secrets.toml`. Please open that file, fill in your token, and let me know when done.
>
> Get your token from: `<direct link from API docs>`

**Stop and wait** for the user to confirm before continuing.

**3c. Verify** with `secrets_view_redacted` — confirm `[sources.<source>].<field>` now shows `***`. If it's still empty, ask the user to check before continuing.

## Step 4 — Run locally

```
uv run python <source>_pipeline.py
```

Report what table was created and how many rows loaded (visible in output).

Then open the local data viewer. Run this command **in the background** (it starts a server and never exits — running it in the foreground will block):

```
uv run dlthub local show
```

This opens the dltHub local UI where the user can browse the loaded rows in DuckDB.

---

## If the job fails

Fix the pipeline file and re-run from Step 4.

| Symptom | Likely cause | Fix |
|---|---|---|
| 0 rows loaded | Wrong `data_selector` | Check raw response shape in output; update key or omit entirely |
| 401 / 403 error | Auth misconfigured | Verify credential is in `secrets.toml` (not `dev.secrets.toml`) and header name/location are correct |
| Script runs indefinitely | Paginator looping | Add `"paginator": "single_page"` to the resource's `endpoint` config |
| `ConfigFieldMissingException` | Secret key path mismatch | Check that `dlt.secrets["sources.<source>.<field>"]` matches the `[sources.<source>]` section in `secrets.toml` |
| `from dlt.hub import run` error | `dlt[hub]` not installed | Run `uv add "dlt[hub]"` |