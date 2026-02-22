# New ingestion pipeline

## Core workflow

0. **Find source** (`find-source`) — discover the right dlt source for the user's data provider
1. **Create pipeline** (`create-rest-api-pipeline`) — scaffold, write code, configure credentials
2. **Debug pipeline** (`debug-pipeline`) — run it, inspect traces and load packages, fix errors
3. **Validate data** (`validate-data`) — inspect schema and data, fix types and structures, iterate until user is satisfied

## Extend and harden

4. **Adjust endpoint** (`adjust-endpoint`) — add pagination, remove limits, add hints, mappings, correct schema etc.
5. **Add incremental loading** — set up `dlt.sources.incremental`, merge keys, and lag windows for production efficiency
6. **Add endpoints** (`new-endpoint`) — add more resources to the source
7. **View data** (`view-data`) — show data to the user & query and explore loaded data in Python

## Related toolkits
- **data-exploration** — for deeper data exploration, interactive marimo notebooks, and reports
