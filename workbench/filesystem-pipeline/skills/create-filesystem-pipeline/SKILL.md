---
name: create-filesystem-pipeline
description: Create a dlt filesystem pipeline that reads files (CSV, Parquet, JSONL, or custom) from local disk, S3, GCS, Azure, or SFTP into a destination. Use for the filesystem core source. Not for REST APIs (rest_api) or databases (sql_database).
argument-hint: "[destination]"
---

# Create a filesystem dlt pipeline

Create the simplest working dlt filesystem pipeline — a single bucket, a single file pattern, a single reader — to get data flowing fast.

The argument is the destination (e.g. `duckdb`, `postgres`, `filesystem`). Defaults to `duckdb` if omitted.

## Steps

### 1. Gather inputs

Before scaffolding, check session context — if the user has already stated any of these values (destination, file format, backend, and bucket url), use them and do not ask again.

Collect all unknown inputs in **one round** — never split into separate back-and-forth turns. The inputs split into two kinds:

**Structured choices** (ask in one round with multipl   e-choice options, up to three parallel questions):
- **Destination** — `duckdb` / `postgres` / `bigquery` / `snowflake` / `filesystem` / etc. Default: `duckdb`. Full list: `https://dlthub.com/docs/dlt-ecosystem/destinations/`.
- **Backend** — `Local` / `S3` / `GCS` / `Azure` / `SFTP`. Determines the dlt extra (`dlt[hub,s3]`, `dlt[hub,gs]`, `dlt[hub,az]`, `dlt[hub,sftp]`; local needs only `dlt[hub]`) and the credential layout.
- **File format** — `CSV` / `Parquet` / `JSONL` / `Custom`. Picks the reader: `read_csv` (needs `pandas`), `read_parquet` (needs `pyarrow`), `read_jsonl`, or a custom `@dlt.transformer`.

**Free-text input** (`bucket_url` — ask as plain text, not structured choices):
- Include it as a plain-text line in the same response as the structured questions, e.g. *"Also please share your bucket URL (e.g. `s3://my-bucket/data/`) in your reply."*
- If the user does not have a bucket / files yet, stop and ask them to provide one — do **not** invent a bucket URL.

Do **not** ask about layout (single vs multi-table). Assume **single-table** — all files matched by the glob share one schema and load into one destination table. The confirmation in step 1b is the user's chance to correct that assumption.

### 1b. Confirm the plan

Before running anything, lay out the plan and ask the user to confirm. Include:

- Working directory (current `pwd`)
- The exact `dlthub pipeline init` command that will run
- Backend, file format, reader (`read_csv` / `read_parquet` / `read_jsonl` / custom)
- `bucket_url`
- `file_glob` — infer a sensible default from the bucket URL, file format, and any domain context (e.g. `*.csv` for CSV format, `**/*.parquet` for nested Parquet). Present it clearly so the user can correct it.
- Pipeline name, dataset name, destination table name (you choose sensible defaults from the source domain — e.g. bucket path or glob hint)
- That secrets will be written as **placeholders only** via MCP and the user fills real values

End the confirmation with a single sentence flagging the single-table assumption and the default table name, e.g.:

> "I'm assuming all files matched by `<glob>` belong to the **same logical table**, which I'll call `files` by default. If you'd like a different name, say so now. If your bucket actually contains multiple distinct tables in different sub-folders (e.g. `reports/*.csv` and `transactions/*.csv` going into separate tables), say so now and I'll use the multi-table pattern instead (step 4b)."

Ask for confirmation with three options: `Confirm — proceed` / `It's actually multi-table` / `Change something`. Only continue past this step on explicit confirmation.

**Do not run `dlthub pipeline init` until the user confirms.**

### 2. Scaffold in the current working directory

While `dlthub pipeline init` runs (below), fetch the relevant docs in parallel based on what the user chose in step 1:
- **If backend is not Local**: Basic configuration & credentials — `https://dlthub.com/docs/dlt-ecosystem/verified-sources/filesystem`
- **If backend is SFTP**: SFTP destination setup — `https://dlthub.com/docs/dlt-ecosystem/destinations/filesystem#sftp`
- **If file format is Custom**: Advanced (custom readers, transformers, glob patterns) — `https://dlthub.com/docs/dlt-ecosystem/verified-sources/filesystem#create-your-own-readers`

Run `dlthub pipeline init` directly in current directory. Pipeline artifacts (`.dlt/`, the `.duckdb` file, generated Python) belong in the user's working directory so they can version-control or move them.

```bash
ls -la                                        # snapshot before scaffolding
uv run dlthub --non-interactive pipeline init filesystem <destination>
ls -la                                        # confirm what was created
```

Note: `--non-interactive` is a global flag on `dlthub` and may appear at any position in the command. Always pass it to prevent prompts that block execution.

If the command fails with `invalid choice: 'pipeline'`, the dlthub workspace is not initialized. Run `uv run dlthub init` and follow its instructions — most importantly run `uv sync` to pull required dependencies — then retry.

`dlthub pipeline init` is safe to re-run in a project that already has files — it adds new ones without overwriting `filesystem_pipeline.py`, and updates shared files (`.dlt/secrets.toml`, `.dlt/config.toml`, `.gitignore`).

The scaffold creates:
- `filesystem_pipeline.py` — kitchen-sink demo with 7 functions; you will replace it
- `.dlt/config.toml` — `[sources.filesystem]` with placeholder `bucket_url`
- `.dlt/secrets.toml` — placeholder credentials (AWS by default; replace with your backend's shape)

### 3. Read the scaffold

Read these to confirm shape and pick patterns to keep:
- `filesystem_pipeline.py` — useful for the `filesystem(...) | read_csv()` pipe pattern; ignore the `readers(...).read_csv()` style and the 7-function demo
- `.dlt/config.toml`

Do **not** read `.dlt/secrets.toml` directly — use the MCP tools (step 6b).

### 4. Replace the pipeline with a focused function

Edit `filesystem_pipeline.py`. Pick the pattern that matches the **Layout** chosen in step 1.

#### 4a. Single-table layout

Use this when all matched files share one schema and load into one destination table.

```python
"""dlt filesystem pipeline: load <files> from <bucket> into <destination>."""

import dlt
from dlt.sources.filesystem import filesystem, read_csv  # or read_parquet / read_jsonl


def load_<table_name>() -> None:
    """Load files from the configured bucket into <destination>.

    bucket_url is read from .dlt/config.toml under [sources.filesystem].
    file_glob is set inline so it lives next to the code that depends on it.
    """
    pipeline = dlt.pipeline(
        pipeline_name="<pipeline_name>",
        destination="<destination>",
        dataset_name="<dataset>",
        dev_mode=True,                              # fresh dataset on every run during dev
    )

    reader = (filesystem(file_glob="<pattern>") | read_csv()).with_name("<table_name>")

    load_info = pipeline.run(reader, write_disposition="replace")
    print(load_info)
    print(pipeline.last_trace.last_normalize_info)


if __name__ == "__main__":
    load_<table_name>()
```

Rules:
- `bucket_url` is injected from `[sources.filesystem]` in `config.toml` (step 6a). `file_glob` is **passed inline** in the script — keeping the pattern next to the code that depends on it makes the pipeline self-documenting and easier to refactor when patterns change.
- `.with_name("<table_name>")` controls the destination table name. Without it, dlt names tables after the resource (`encounters` for `read_csv`).
- Start with `replace` write disposition + `dev_mode=True`. Switch to `merge` / incremental later (see advanced docs).
- One file format per pipeline at first. Mixing CSV and Parquet means two readers and two `.with_name(...)` calls — leave that for iteration 2.

#### 4b. Multi-table layout

Use this when different sub-folders / glob patterns map to different destination tables. **Reuse the same `filesystem(...) | read_csv()` pipe per table — `.with_name("<table>")` is what splits them into separate destination tables.** Without renaming, all readers of the same kind would collide into one table.

```python
"""dlt filesystem pipeline: load multiple tables from <bucket> into <destination>."""

import dlt
from dlt.sources.filesystem import filesystem, read_csv  # or read_parquet / read_jsonl

BUCKET_URL = "<scheme>://<bucket>"

def load_all() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="<pipeline_name>",
        destination="<destination>",
        dataset_name="<dataset>",
        dev_mode=True,
    )

    reports = (
        filesystem(bucket_url=BUCKET_URL, file_glob="reports/*.csv")
        | read_csv()
    ).with_name("reports")

    transactions = (
        filesystem(bucket_url=BUCKET_URL, file_glob="transactions/*.csv")
        | read_csv()
    ).with_name("transactions")

    load_info = pipeline.run([reports, transactions], write_disposition="replace")
    print(load_info)
    print(pipeline.last_trace.last_normalize_info)


if __name__ == "__main__":
    load_all()
```

Rules for multi-table:
- Pass `bucket_url` and `file_glob` **inline as kwargs** — `[sources.filesystem]` in `config.toml` is one global value and can't differ per call. Step 6a's config.toml fragment is for single-table only.
- Same backend credentials still come from `[sources.filesystem.credentials]` in `secrets.toml`.
- One reader type per call (`read_csv`, `read_parquet`, etc.) — mix freely if different sub-folders use different formats.
- Pass the renamed pipes as a **list** to `pipeline.run([reports, transactions, ...])`.

Reference for renaming/duplicating resources: `https://dlthub.com/docs/general-usage/resource.md`.

### 5. Custom readers (only if format is Custom)

Skip this step for CSV/Parquet/JSONL.

Write a `@dlt.transformer` that accepts an `Iterator[FileItemDict]` and yields records. Use `file_obj.open()` to access the file content — `FileItemDict` also exposes `file_name`, `file_url`, and `relative_path` as metadata keys.

Skeleton (replace the body with format-specific parsing):

```python
from typing import Iterator
import dlt
from dlt.sources.filesystem import FileItemDict
from dlt.sources import TDataItems

@dlt.transformer
def read_<format>(items: Iterator[FileItemDict]) -> Iterator[TDataItems]:
    for file_obj in items:
        with file_obj.open() as f:
            # parse f and yield records as a list of dicts
            yield [...]
```

Wire it into the pipeline the same way as a built-in reader:

```python
reader = (filesystem(file_glob="<pattern>") | read_<format>()).with_name("<table_name>")
```

Use the advanced docs (fetched above) for format-specific parsing examples (Excel, XML, etc.). If the format needs a third-party library, install it with `uv add <library>` before running.

### 6. Configure

#### 6a. config.toml (non-secret values)

**Single-table only.** For multi-table layout (4b), `bucket_url` is passed inline in code — skip this step entirely.

Edit `.dlt/config.toml` directly. Set **only `bucket_url`** under `[sources.filesystem]`. `file_glob` lives in the script (step 4a), not here:

```toml
[sources.filesystem]
bucket_url = "<scheme>://<bucket>/<optional-path>"
```

The scaffold's `local_dir = "<configure me>"` line is unused for cloud backends — leave or remove.

#### 6b. Secrets — MCP only, never edit secrets.toml directly

**Never read or write `.dlt/secrets.toml` directly. Never run commands that print secret values** (`cat`, `env | grep`, `gcloud auth print-access-token`, etc.).

**Do not ask the user which auth method to use.** Pick the standard placeholder for the backend (below) and call `secrets_update_fragment` immediately. The user edits the real values themselves — they can adjust the auth method then if needed.

Use `dlt-workspace-mcp` tools — `secrets_list`, `secrets_view_redacted`, `secrets_update_fragment` — to write **placeholders only**. The user fills the real values themselves by editing the file. (See the `setup-secrets` skill for full details.)

Per-backend placeholder fragments (pass via `secrets_update_fragment`):

**S3:**
```toml
[sources.filesystem.credentials]
aws_access_key_id     = "AKIA-fill-me-in"
aws_secret_access_key = "fill-me-in"
```
Where: AWS Console → IAM → Users → *your user* → Security credentials → *Create access key*. Use a user/role with `s3:GetObject` and `s3:ListBucket` on the target bucket.

**GCS** (no anonymous mode — even public buckets need a service-account JSON):
```toml
[sources.filesystem.credentials]
project_id   = "your-gcp-project-id"
client_email = "sa-name@your-project.iam.gserviceaccount.com"
private_key  = """-----BEGIN PRIVATE KEY-----
fill-me-in
-----END PRIVATE KEY-----
"""
```
Where: Google Cloud Console → IAM & Admin → Service Accounts → *Create or select* → grant role `Storage Object Viewer` on the bucket → *Keys → Add Key → JSON*. Copy `project_id`, `client_email`, `private_key` from the downloaded JSON.

**Azure:**
```toml
[sources.filesystem.credentials]
azure_storage_account_name = "your-account"
azure_storage_account_key  = "fill-me-in"
```
Where: Azure Portal → Storage Account → *Access keys*. Copy the account name and one of the two keys.

**SFTP** (key-based):
```toml
[sources.filesystem.credentials]
sftp_username       = "your-user"
sftp_key_filename   = "/abs/path/to/id_rsa"
sftp_key_passphrase = "fill-me-in-or-remove"
```
Where: from your existing SSH key or the server admin.

**Local filesystem:** no credentials needed — skip 6b entirely.

After running `secrets_update_fragment`, **show the user a summary of changed files and tell them which fields to fill** before continuing.

### 7. Ask before running

If the backend is not Local, **explicitly remind the user to fill in their credentials in `.dlt/secrets.toml` before proceeding** — the pipeline will fail with a `ConfigFieldMissingException` if the placeholders are still there.

**Enumerate the files before asking how to run.** `filesystem()` yields individual `FileItemDict` objects with metadata (including `size_in_bytes`) — no data is read or transferred:

```python
from dlt.sources.filesystem import filesystem

items = list(filesystem(file_glob="<pattern>"))
total_mb = sum(f["size_in_bytes"] for f in items) / 1024**2
print(f"{len(items)} files · {total_mb:.1f} MB total · largest: {max(f['size_in_bytes'] for f in items)/1024**2:.1f} MB")
```

For cloud backends this requires real credentials to be filled first. If not yet filled, skip the inventory and default to recommending a sample run.

Use the result to calibrate your recommendation:
- **< 10 files and < 50 MB** — full load is fine; still offer sample as an option
- **≥ 10 files or ≥ 50 MB** — recommend sample first
- **≥ 100 files or ≥ 500 MB** — strongly recommend sample; warn about load time

If the glob matches **zero files**, stop — help the user fix the pattern before offering any run option.

Then ask the user how they want to run:
- **Sample run** — load a single file to verify the pipeline works before committing to a full load.
- **Full load** — load everything now.

For a sample run, set `files_per_page=1` **and** `.add_limit(1)` on the `filesystem(...)` call — always both, regardless of whether you use a built-in reader or a custom transformer. `add_limit(1)` limits to 1 yield from the resource generator; `files_per_page` (default 100) controls how many files are in each yield, so without `files_per_page=1` you'd still load up to 100 files:

```python
# built-in reader
files = filesystem(file_glob="<pattern>", files_per_page=1).add_limit(1)
reader = (files | read_csv()).with_name("<table_name>")

# custom transformer — same rule, files_per_page=1 must not be omitted
files = filesystem(file_glob="<pattern>", files_per_page=1).add_limit(1)
reader = files | read_<format>()
```

Show a summary of changed files and the planned run command. Only run when the user confirms.

### 8. Debug — first run

When the user confirms, run `uv run python filesystem_pipeline.py`. Common first-run failures:

| Error | Fix |
|-------|-----|
| `You must install additional dependencies to run filesystem` | Install the backend extra: S3 → `uv add "dlt[hub,s3]"`, GCS → `uv add "dlt[hub,gs]"`, Azure → `uv add "dlt[hub,az]"`, SFTP → `uv add "dlt[hub,sftp]"`. |
| `No module named 'pandas'` (or `pyarrow`) | Run `uv add pandas` / `uv add pyarrow`. |
| `ConfigFieldMissingException` for credential fields | The user hasn't filled `secrets.toml` — point them at the file and the placeholders from 6b. |
| `bucket_url` resolved to `<configure me>` | `config.toml` was not updated — go back to 6a. |
| `FileNotFoundError` / empty load | `file_glob` doesn't match anything — list the bucket with the `fsspec_from_resource` helper from the advanced docs, or relax the pattern. |

After a clean run, verify the load:
- `list_tables`, `get_row_counts`, `preview_table` MCP tools (preferred), or
- `dlthub local pipeline show <pipeline_name>` for a quick browser dashboard.

If this was a sample run, ask the user if they want to do a full load now — remove `.add_limit(1)` and `files_per_page=1` from the pipeline and run again.

**Do not add a second reader, incremental loading, or merge keys until the single-resource pipeline runs end-to-end and the user has reviewed the loaded data.**

For failures not covered above (schema errors, bad data types, failed jobs, normalisation issues), hand off to the **rest-api-pipeline** toolkit's `debug-pipeline` skill — it covers post-run trace inspection, load package analysis, and iterative fixes.

Once the pipeline is verified, suggest next steps in this order:
1. **Add incremental loading** (`add-incremental-loading`) — load only new or modified files on each run
2. **Optimize performance** (`optimize-filesystem-performance`) — if reading files is slow or memory-heavy (faster reader, chunked streaming, parallel reads, glob narrowing)
3. **Explore the data** — hand off to **data-exploration** toolkit to profile and visualise the loaded tables
4. **Add data quality checks** — hand off to **data-quality** toolkit
5. **Deploy** — hand off to **dlthub-platform** toolkit to schedule the pipeline on dltHub
