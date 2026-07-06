---
name: rest-api-pipeline
description: Build a dlt pipeline that loads data from a REST API or HTTP endpoint.
  Use when the user wants to ingest from Stripe, GitHub, Salesforce, HubSpot, or any
  web service with an HTTP API. DO NOT USE for SQL databases (use sql-database-pipeline)
  or local/cloud files (use filesystem-pipeline).
---

Your identity and guardrails (SOUL) are already loaded via the `init` base toolkit — operate from them, especially on secrets, sampling, and running from the project root.

## Before you start

Requires a dlthub workspace. Verify with `uv run dlthub ai status`. If the
workspace or dlt isn't set up, help the user initialize one before continuing.

For dlt itself: read https://dlthub.com/docs/llms.txt and follow it to the
REST API source — https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic.md

## Workflow

### Step 1 — Find or scaffold the source
Identify the API and search for an existing verified/REST source. If none fits, read the provider's own API documentation to gather the four things a `rest_api` source needs: the **base URL**, the **authentication** scheme, the **pagination** style (cursor, offset/page, link header, …), and the **endpoints** (paths) to load. Then scaffold the `rest_api` source from those, as a single runnable Python file, and install the destination's extra (`uv add "dlt[<destination>]"`) so the first run doesn't fail on a missing dependency.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic.md (config shape), https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced.md (paginators and auth options), and https://dlthub.com/docs/dlt-ecosystem/destinations/ (destination extras)
✓ Done when: a single runnable source file specifies the base URL, paginator, and endpoints — and the user has the required API credentials.

### Step 2 — Configure credentials
Set up the source's auth and the destination connection through the workspace secrets tools. Make sure to use the mcp and never read or write credentials yourself.
→ Docs: https://dlthub.com/docs/general-usage/credentials/setup.md
✓ Done when: a pipeline run gets past auth without raising a credentials error.

### Step 3 — Run on a sample
Run the pipeline under `dev_mode=True` with a row-count limit — `add_limit(n, count_rows=True)`, never a page-based limit, which can overshoot badly on APIs with large pages — to validate output before a full load. Keep this run plain — no incremental cursors, merge keys, or production filtering yet; those come in Step 5 after the user confirms the data.
→ Docs: https://dlthub.com/docs/general-usage/resource#sample-from-large-data (row-count limiting) and https://dlthub.com/docs/general-usage/pipeline#do-experiments-with-dev-mode
✓ Done when: the pipeline completes without errors and at least one table is loaded with the expected schema.

### Step 4 — Inspect and confirm
Show the user the loaded tables, row counts, and schema through the dlt dataset API. Get confirmation the data looks right before proceeding.
→ Docs: https://dlthub.com/docs/hub/data-discovery/datasets
✓ Done when: the user confirms the data looks correct.

### Step 5 — Run full load
Configure incremental loading where the source supports it — pick the cursor from the schema inspected in Step 4 (e.g. an updated-timestamp field). Then remove the sample limit, switch off `dev_mode`, and run the full pipeline. If earlier runs left the dev namespace polluted (pending load packages, schema conflicts), run into a fresh dataset instead of migrating broken state.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced.md
✓ Done when: a full run completes and row counts, checked through the dataset API, match expectations.

## What's next

- Data loaded successfully → the pipeline is ready for scheduling or transformation.
- User wants to explore the data → point them to the dlt dataset API and dashboard (https://dlthub.com/docs/hub/data-discovery/datasets).
- User wants to schedule or deploy → outside this toolkit's scope (requires dltHub Platform).
