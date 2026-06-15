# One-shot workflow

## Workflow Entry
**ALWAYS** start with `run-sample-pipeline`

## Core workflow
1. **Run sample pipeline** (`run-sample-pipeline`) — run the pre-made GitHub pipeline against DuckDB and start `dlthub local show` so the user can see their data in the browser.
2. **Test deployment** (`test-deployment`) — set up a cloud destination, deploy the pipeline to dltHub Platform, and verify it runs on the cloud.

## Handover between skills
When `run-sample-pipeline` completes, end with this message to the user:

> Your data is loaded. Explore the tables in the UI — run a query, check the schema, get a feel for what's there. When you're ready to deploy this to the cloud, just say so.

Then wait. Do not proceed to `test-deployment` until the user explicitly says they are ready.

When they do, invoke `test-deployment` immediately. This workflow has exactly two steps — there is nothing between them and nothing alongside them.

## Handover To Other Toolkits
Only surface these after both `run-sample-pipeline` and `test-deployment` have completed successfully, and only if the user asks what to do next.

- **data-exploration** — "your data is live — want to explore it with charts and a notebook?". Run `uv run dlthub --non-interactive ai toolkit install data-exploration`, then invoke `explore-data`.
- **rest-api-pipeline** — for pagination, incremental loading, or adding more endpoints, or starting with another source entirely. Run `uv run dlthub --non-interactive ai toolkit install rest-api-pipeline` first, then invoke `adjust-endpoint` or `new-endpoint`.