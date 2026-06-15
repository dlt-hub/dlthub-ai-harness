# One-shot workflow

## Workflow Entry
**ALWAYS** start with `run-sample-pipeline`

## Core workflow
1. **Run sample pipeline** (`run-sample-pipeline`) — run the pre-made GitHub pipeline against DuckDB and open `dlthub local show` so the user can see their data.
2. **Test deployment** (`test-deployment`) — set up a cloud destination, deploy the pipeline to dltHub Platform, and verify it runs on the cloud.

## Handover between skills
When `run-sample-pipeline` completes (user can see data in `dlthub local show`), the next and only step is `test-deployment`. Invoke it immediately.

This workflow has exactly two steps. There is nothing between them and nothing alongside them.

## Outgoing handovers
Only surface these after **both** `run-sample-pipeline` and `test-deployment` have completed successfully, and only if the user asks what to do next.

- **data-exploration** — "your data is live — want to explore it with charts and a notebook?". Run `uv run dlthub --non-interactive ai toolkit install data-exploration`, then invoke `explore-data`.
- **rest-api-pipeline** — for pagination, incremental loading, or adding more endpoints, or starting with another source entirely. Run `uv run dlthub --non-interactive ai toolkit install rest-api-pipeline` first, then invoke `adjust-endpoint` or `new-endpoint`.