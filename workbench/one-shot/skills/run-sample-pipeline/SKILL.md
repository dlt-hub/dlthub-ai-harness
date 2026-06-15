---
name: run-sample-pipeline
description: Run the pre-made GitHub pipeline against DuckDB and open the dltHub local UI. Use when the user wants to get started with dlthub or run the sample pipeline.
argument-hint: ""
---

Run a pre-made pipeline that loads issues and pull requests from the `dlt-hub/dlt` GitHub repository into DuckDB. No credentials required.

## Step 1 — Write the pipeline file

Create `github_pipeline.py` in the project root:

```python
"""GitHub dlt pipeline.

Loads issues and pull requests from the dlt-hub/dlt repository into DuckDB.
"""

import dlt
from dlt.sources.rest_api import rest_api_source
from dlt.hub import run


def github():
    return rest_api_source(
        {
            "client": {
                "base_url": "https://api.github.com/",
            },
            "resources": [
                {
                    "name": "issues",
                    "endpoint": {
                        "path": "repos/dlt-hub/dlt/issues",
                        "params": {"state": "all"},
                    },
                    "primary_key": "id",
                },
                {
                    "name": "pull_requests",
                    "endpoint": {
                        "path": "repos/dlt-hub/dlt/pulls",
                        "params": {"state": "all"},
                    },
                    "primary_key": "id",
                },
            ],
        }
    )


@run.pipeline("github_pipeline")
def load_github():
    """Load issues and pull requests from dlt-hub/dlt."""

    pipeline = dlt.pipeline(
        pipeline_name="github_pipeline",
        destination="duckdb",
        dataset_name="github",
    )

    load_info = pipeline.run(github().add_limit(50, count_rows=True), write_disposition="replace")
    print(load_info)


if __name__ == "__main__":
    load_github()
```

## Step 2 — Run the pipeline

```bash
uv run python github_pipeline.py
```

Report the tables created and row counts from the output.

## Step 3 — Open the local UI

Run this in the background (it starts a server and never exits):

```bash
uv run dlthub local show
```

This opens the dltHub UI in the browser automatically.

---

End with this message:

> Your data is loaded and the dltHub UI is open in your browser. Explore the tables — run a query, check the schema, get a feel for what's there. When you're ready to deploy this to the cloud, just say so.

Then wait for the user to signal they are ready before proceeding.

---

## If the pipeline fails

| Symptom | Likely cause | Fix |
|---|---|---|
| 403 / rate limit error | GitHub API rate limit (60 req/hour unauthenticated) | Wait a few minutes and re-run |
| 0 rows loaded | Response shape changed | Check output; omit `data_selector` if set |
| `from dlt.hub import run` error | `dlt[hub]` not installed | Run `uv add "dlt[hub]"` |
