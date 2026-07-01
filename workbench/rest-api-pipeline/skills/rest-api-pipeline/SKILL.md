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
Identify the API and search for an existing verified/REST source. If none fits, read the provider's own API documentation to gather the four things a `rest_api` source needs: the **base URL**, the **authentication** scheme, the **pagination** style (cursor, offset/page, link header, …), and the **endpoints** (paths) to load. Then scaffold the `rest_api` source from those.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic.md (config shape) and https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced.md (paginators and auth options)
✓ Done when: a source Python file exists whose config specifies the base URL, paginator, and endpoints — and the user has the required API credentials.

### Step 2 — Configure credentials
Set up the source's auth and the destination connection through the workspace secrets tools. Make sure to use the mcp and never read or write credentials yourself.
→ Docs: https://dlthub.com/docs/general-usage/credentials/setup.md
✓ Done when: a pipeline run gets past auth without raising a credentials error.

### Step 3 — Run on a sample
Run the pipeline with a row limit or a narrow date range to validate output before a full load.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic.md
✓ Done when: the pipeline completes without errors and at least one table is loaded with the expected schema.

### Step 4 — Inspect and confirm
Show the user the loaded tables, row counts, and schema. Get confirmation the data looks right before proceeding.
→ Docs: https://dlthub.com/docs/general-usage/dataset-access/dataset.md
✓ Done when: the user confirms the data looks correct.

### Step 5 — Run full load
Remove the sample limit and run the full pipeline. Configure incremental loading and pagination if the source supports them.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced.md
✓ Done when: a full run completes and row counts match expectations.

## What's next

- Data loaded successfully → the pipeline is ready for scheduling or transformation.
- User wants to explore the data → point them to the dlt dataset API and dashboard (https://dlthub.com/docs/general-usage/dataset-access/dataset.md).
- User wants to schedule or deploy → outside this toolkit's scope (requires dltHub Platform).
