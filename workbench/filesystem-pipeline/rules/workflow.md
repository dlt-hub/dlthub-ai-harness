# Filesystem pipeline workflow

## Workflow Entry
**ALWAYS** start with **Create filesystem pipeline** (`create-filesystem-pipeline`) SKILL — gather inputs, scaffold, configure credentials, and run the pipeline

## Core workflow
1. **Create pipeline** (`create-filesystem-pipeline`) — scaffold with `dlthub pipeline init filesystem`, configure bucket URL, credentials, file glob, and reader; run and verify the load

## Extend and harden
2. **Debug pipeline** — for failures beyond first-run errors, use the `troubleshoot-pipeline-run` skill from `init`
3. **Add incremental loading** (`add-incremental-loading`) — filter files by modification date, optionally filter records by timestamp column, switch to merge write disposition
4. **Optimize performance** (`optimize-filesystem-performance`) — when reading files is slow or memory-heavy: choose a faster reader, stream in chunks, read files in parallel, narrow the glob