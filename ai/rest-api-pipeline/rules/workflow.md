# New ingestion pipeline

## Core workflow

0. **Find source** (`find-source`) — discover the right dlt source for the user's data provider
1. **Create pipeline** (`create-pipeline`) — scaffold, write code, configure credentials
2. **Debug pipeline** (`debug-pipeline`) — run it, inspect traces and load packages, fix errors
3. **Validate data** (`validate-data`) — inspect schema and data, fix types and structures, iterate until user is satisfied

## Extend and harden

4. **Add endpoints** (`add-endpoint`) — add more resources to the source
5. **Add incremental loading** — set up `dlt.sources.incremental`, merge keys, and lag windows for production efficiency
6. **View data** (`view-data`) — query and explore loaded data in Python
7. **Create report** (`create-report`) — create marimo notebook for interactive analysis and visualization

## Cross-references

- `create-pipeline` → on first run, use `debug-pipeline` to verify structure
- `debug-pipeline` → if `ConfigFieldMissingException`, check TOML sections and credential setup from `create-pipeline` step 6b. If credentials are wrong or unknown, research the data source (like `find-source` does).
- `debug-pipeline` → if pipeline loads successfully, move to `validate-data`
- `validate-data` → if data shape needs changes, re-run pipeline with `debug-pipeline` after edits
- `validate-data` → when user is happy, suggest `add-endpoint` for more resources, `view-data` for querying, or `create-report` for visualization
- `add-endpoint` → after adding, use `debug-pipeline` + `validate-data` to verify the new resource
- `view-data` → provides the data access API used by `create-report`
