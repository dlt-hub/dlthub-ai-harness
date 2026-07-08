---
name: optimize-filesystem-performance
description: Speed up a dlt filesystem pipeline. Use when reading files (CSV, Parquet, JSONL) from local disk, S3, GCS, Azure, or SFTP is slow or memory-heavy and the user wants to optimize it — choose a faster reader, read files in parallel, narrow the glob, or stream in chunks. For first-time incremental/merge setup, or to skip files already loaded in previous runs, use add-incremental-loading instead.
argument-hint: "[pipeline-name] [symptom]"
---

# Optimize filesystem extraction

Source-specific tuning for `filesystem` pipelines. Work the loop — **diagnose → pick the fix → apply → measure → repeat**, one change at a time. Combine these with the source-agnostic stage levers in the **performance** toolkit's `optimize-performance` skill.

**Essential reading:** https://dlthub.com/docs/dlt-ecosystem/verified-sources/filesystem

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline. If omitted, infer from session context; if ambiguous, ask and stop.
- `symptom` (optional): e.g. "reading thousands of CSVs is slow", "OOM on a big file", "scanning the whole bucket".

## 1. Diagnose

- **Measure first.** Read extract time from `pipeline.last_trace` (or `progress="log"`); confirm reading files is the slow stage (if normalize/load dominates, that's the **performance** toolkit).
- **Gate — skip files you already loaded.** If the pipeline re-reads the whole bucket every run, set up file-level incremental (filter by `modification_date`) first — see `add-incremental-loading`. Reading fewer files beats reading them faster.
- **Name the bottleneck:** slow format/parsing (CSV)? whole file pulled into memory (OOM)? many files read one-by-one? listing a bucket with very many files? scanning far more objects than you need? or just moving files where you don't need to parse them at all?

## 2. Pick the fix

Match the symptom to a lever. They **compose** — apply every one that fits; just don't tune what isn't the bottleneck.

| Symptom | Fix (see Apply) |
|---|---|
| CSV parsing is slow / you control the source format | Prefer Parquet; use a faster reader |
| OOM — whole file loaded into memory | Stream in chunks |
| Many files read sequentially | `.parallelize()` reads |
| Lists/scans the whole bucket | Narrow the glob |
| Listing a bucket with very many files | Raise `files_per_page` |
| You only need to move files, not parse them | Skip the reader — copy via fsspec |

## 3. Apply

**Faster format / reader** — read speed by format is **Parquet > JSONL > CSV**; land Parquet if you control the source. Pipe the filesystem resource to a reader:
- `read_parquet()` — streams row groups; `use_pyarrow=True` for zero-copy Arrow.
- CSV: `read_csv_duckdb()` (duckdb-backed — faster and lower-memory than the pandas `read_csv()`; `use_pyarrow=True` yields Arrow), or `read_csv()` (pandas, forwards `**pandas_kwargs`).
- `read_jsonl()`.
```python
from dlt.sources.filesystem import filesystem, read_csv_duckdb
reader = (filesystem(bucket_url="<url>", file_glob="<pattern>") | read_csv_duckdb(use_pyarrow=True))
```

**Stream in chunks** — all readers batch: `read_csv(chunksize=...)` (pandas, default 10000), `read_csv_duckdb(chunk_size=...)` (default 5000), `read_parquet(chunksize=...)` / `read_jsonl(chunksize=...)` (default 1000). Lower it to cut memory on wide files; raise it to reduce overhead on narrow files. For files too big for even a chunked built-in reader — or a format they don't cover — write a custom transformer that streams and yields chunks:
```python
@dlt.transformer
def read_big_csv(items, chunksize=10000, **kwargs):
    import pandas as pd
    for f in items:                        # f is a FileItemDict
        for df in pd.read_csv(f.open(), chunksize=chunksize, **kwargs):
            yield df.to_dict(orient="records")

reader = filesystem(bucket_url="<url>", file_glob="<pattern>") | read_big_csv
```
**Read files concurrently** — only worth it for **remote/object-store** reads (local files are CPU/GIL-bound — use Parquet / `read_csv_duckdb` / more `[normalize] workers` there). `.parallelize()` splits reads **across pages**, so it needs several pages: set `files_per_page` well below your file count **and** call `.parallelize()`. At the default `files_per_page=100`, `.parallelize()` does nothing until you have >100 files (and under-uses workers otherwise).
```python
reader = (filesystem(bucket_url="<url>", file_glob="<pattern>", files_per_page=10) | read_csv()).parallelize()
```
Concurrency is capped by `[extract] workers` — pick `files_per_page` for a few pages per worker, not 1 file per page. (Instead **raise** `files_per_page` if *listing* a huge bucket is the bottleneck, not reading.)

**Narrow the glob** — the cheapest win is reading fewer files. Make `file_glob` as specific as possible (path prefixes, date partitions, extensions) so dlt never lists or fetches irrelevant objects — important on object stores where listing is slow.

**Just moving files? skip parsing** — if you don't need the contents (e.g. copying files to another bucket), don't pipe to a reader at all. Use fsspec directly to avoid parse + memory entirely:
```python
from dlt.sources.filesystem import filesystem
from dlt.sources.filesystem.helpers import fsspec_from_resource
files = filesystem(bucket_url="<url>", file_glob="<pattern>")
fs = fsspec_from_resource(files)            # authenticated fsspec client for bulk ops
# per item: item.open() / item.read_bytes()
```

## 4. Measure, then repeat

- Re-run and compare extract time in `pipeline.last_trace` against step 1.
- **Errors on large files / under concurrency** → see `create-filesystem-pipeline` "Debug — first run" (it escalates to **rest-api-pipeline** → `debug-pipeline` for anything it doesn't cover).
- **Stop or repeat — check in, don't loop autonomously.** Report the before/after to the user, then:
  - **Stop** when it meets the user's goal (fast enough / fits memory), the last lever gave **no meaningful improvement** (diminishing returns), or you've hit an external ceiling (object-store throughput, network bandwidth) that tuning can't move.
  - **Repeat** with the next matching lever, one at a time. "Fast enough" is the user's call — a minor improvement may already be enough, so confirm before another round rather than chasing micro-gains.

## Next steps

- **Stage-level tuning (workers, buffers, normalize/load parallelism, memory)** → hand over to the **performance** toolkit → `optimize-performance` (install if not present: `uv run dlthub --non-interactive ai toolkit install performance`).
- **Tuned and stable** → hand over to **dlthub-platform** to deploy (install if not present: `uv run dlthub --non-interactive ai toolkit install dlthub-platform`).
