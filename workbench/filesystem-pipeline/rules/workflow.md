# Filesystem pipeline workflow

## Workflow Entry
**ALWAYS** start with **Create filesystem pipeline** (`create-filesystem-pipeline`) SKILL — gather inputs, scaffold, configure credentials, and run the pipeline

## Core workflow
1. **Create pipeline** (`create-filesystem-pipeline`) — scaffold with `dlthub pipeline init filesystem`, configure bucket URL, credentials, file glob, and reader; run and verify the load

## Extend and harden
2. **Debug pipeline** — for failures beyond first-run errors, hand off to **rest-api-pipeline** → `debug-pipeline`
3. **Add incremental loading** (`add-incremental-loading`) — filter files by modification date, optionally filter records by timestamp column, switch to merge write disposition
4. **Optimize performance** (`optimize-filesystem-performance`) — when reading files is slow or memory-heavy: choose a faster reader, stream in chunks, read files in parallel, narrow the glob

## Handover to other toolkits

### Outgoing (from filesystem-pipeline)

- **data-exploration** — after the pipeline runs and data is loaded, when the user wants to explore, chart, or build dashboards from the loaded files
- **data-quality** — after the pipeline runs, when the user wants column-level validation or load metrics on every run
- **dlthub-platform** — when the pipeline is working and the user wants to deploy or schedule it on dltHub
- **rest-api-pipeline** → `debug-pipeline` — for complex pipeline failures (schema errors, failed jobs, normalisation issues) beyond the first-run debug table
- **performance** — after `optimize-filesystem-performance`, when the pipeline works but is slow or memory-heavy and needs source-agnostic stage tuning (extract/normalize/load workers, buffers, file rotation); start at `optimize-performance`

### Incoming (to filesystem-pipeline)

- From **rest-api-pipeline** — when the user's data source turns out to be file-based rather than a REST API; pipeline name and destination may already be known