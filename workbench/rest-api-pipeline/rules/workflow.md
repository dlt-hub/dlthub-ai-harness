# New ingestion pipeline

## Workflow Entry
**ALWAYS** start with **Find source** (`find-source`) SKILL — discover the right dlt source for the user's data provider

## Core workflow
1. **Create pipeline** (`create-rest-api-pipeline`) — scaffold, write code, configure credentials. For a verified source, `find-source` (step 8) scaffolds it with `dlthub pipeline init` instead, then continue at **Debug pipeline**
2. **Debug pipeline** (`debug-pipeline`) — run it, inspect traces and load packages, fix errors
3. **Validate data** (`validate-data`) — inspect schema and data, fix types and structures, iterate until user is satisfied

## Extend and harden

4. **Adjust endpoint** (`adjust-endpoint`) — add pagination, remove limits, add hints, mappings, correct schema etc.
5. **Add incremental loading** (`adjust-endpoint`) — set up `dlt.sources.incremental`, merge keys, and lag windows for production efficiency
6. **Add endpoints** (`new-endpoint`) — add more resources to the source
7. **View data** (`view-data`) — show data to the user & query and explore loaded data in Python
8. **Optimize performance** (`optimize-rest-api-performance`) — when the pipeline works but is slow: parallelize child resources, raise page size, run resources concurrently, tune retries
