---
name: run-sample-pipeline
description: Build and run a GitHub issues pipeline against DuckDB and open the dltHub local UI. Use when the user wants to load GitHub issues from a repository into DuckDB.
argument-hint: ""
---

Load the most recent GitHub issues from the repository in the user's prompt into DuckDB. No credentials required.

## Step 1 — Extract the repository details

Parse the GitHub URL from the user's prompt to extract `{owner}` and `{repo}`.

For example: `https://github.com/dlt-hub/dlt` → `owner = dlt-hub`, `repo = dlt`

## Step 2 — Write the pipeline file

Create `github_pipeline.py` in the project root, substituting `{owner}` and `{repo}`:

```python
"""GitHub dlt pipeline.

Loads the most recent issues from {owner}/{repo} into DuckDB.
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
                        "path": "repos/{owner}/{repo}/issues",
                        "params": {
                            "state": "all",
                            "sort": "created",
                            "direction": "desc",
                        },
                    },
                    "primary_key": "id",
                },
            ],
        }
    )


@run.pipeline("github_pipeline")
def load_github():
    """Load the most recent issues from {owner}/{repo}."""

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

## Step 3 — Run the pipeline

```bash
uv run python github_pipeline.py
```

Report the table created and row count from the output.

## Step 4 — Open the local UI

Run the following command in a parallel task — do not wait for it to complete:

```bash
uv run dlthub local show
```

Continue to the next step immediately.

---

End with this message:

> Your data is loaded. Explore the issues table in the UI — run a query, check the schema, get a feel for what's there. When you're ready to deploy this to the cloud, just say so.

Then wait for the user to signal they are ready before proceeding.

---

## If the pipeline fails

| Symptom | Likely cause | Fix |
|---|---|---|
| 403 / rate limit error | GitHub API rate limit (60 req/hour unauthenticated) | Wait a few minutes and re-run |
| 0 rows loaded | Response shape changed | Check output; omit `data_selector` if set |
| `from dlt.hub import run` error | `dlt[hub]` not installed | Run `uv add "dlt[hub]"` |
