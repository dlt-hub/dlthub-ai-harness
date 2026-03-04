---
name: create-rest-api-pipeline
description: Create a dlt REST API pipeline. Use for the rest_api core source, or any generic REST/HTTP API source. Not for sql_database or filesystem sources.
argument-hint: "[dlt-init-command]"
---

# Create a rest api dlt pipeline

Create the simplest working dlt pipeline — single endpoint, no pagination or incremental loading — to get data flowing fast.

**Requires a `dlt init` command as the argument** (e.g. `dlt init shopify_store duckdb`).
If you don't have one yet, run `find-source` first to identify the right source.

The argument is the full `dlt init` command to run (e.g. `dlt init shopify_store duckdb` or `dlt init sql_database postgres`).

## Steps

### 1. Snapshot current folder

Run `ls -la` to see the current state before scaffolding.

### 2. Run dlt init

`dlt init` can be run multiple times in the same project — each run adds new files without overwriting existing pipeline scripts. It will update shared files (`.dlt/secrets.toml`, `.dlt/config.toml`, `requirements.txt`, `.gitignore`).

Run the provided `dlt init` command with `--non-interactive` in the active venv. Depending on the source type, this creates:

**Core source** (`dlt init rest_api duckdb`):
- `rest_api_pipeline.py` (or similar) — full working example with RESTAPIConfig, pagination, incremental loading

**Generic fallback** (`dlt init <unknown_name> duckdb`):
- `<name>_pipeline.py` — basic intro template (less useful, prefer core sources)

**Shared files** (created on first init, updated on subsequent runs):
- `.dlt/secrets.toml` — credentials template
- `.dlt/config.toml` — pipeline config
- `requirements.txt` — Python dependencies
- `.gitignore`

Run `ls -la` again to confirm what was created.

### 3. Read generated files

Read the following files to understand the scaffold:
- `<source>_pipeline.py` — the pipeline code template
- `<source>-docs.yaml` — API endpoint scaffold with auth, endpoints, params, data selectors (if present)
- `.dlt/config.toml` — source/destination config ie. `api_url`

Do NOT read the `.md` file or any `secrets.toml` file.

### 4. Research before writing code

Do these in parallel:

**Read essential dlt docs upfront:**
- REST API source (config, auth, pagination, processing_steps): `https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic.md`
- Source & resource decorators, parameters: `https://dlthub.com/docs/general-usage/source.md` and `https://dlthub.com/docs/general-usage/resource.md`

**Web search the data source:**
- Confirm the scaffold is accurate, learn about auth method, available endpoints
- How does the user get API keys/tokens for this service

**Read additional docs as needed in later steps:**
- How dlt works (extract → normalize → load): `https://dlthub.com/docs/reference/explainers/how-dlt-works.md`
- CLI reference (trace, load-package, schema): `https://dlthub.com/docs/reference/command-line-interface.md`
- File formats: `https://dlthub.com/docs/dlt-ecosystem/file-formats/`
- Full docs index: `https://dlthub.com/docs/llms.txt`

### 5. Present your findings
Present your findings so user can pick **ONE** of the endpoints that you will implement. Answer questions, do more
research if needed.

### 6. Create pipeline with single endpoint

Edit `<source>_pipeline.py` using information from the scaffold, API research, and dlt docs:

- Focus on a single endpoint, ignore pagination and incremental loading for now
- Configure `base_url` and `auth`
- Add resources with `endpoint.path`, `data_selector`, `params`, `primary_key`
- Use `dev_mode=True` on the pipeline (fresh dataset on every run during debugging)
- Use `.add_limit(1)` on the source when calling `pipeline.run()` (load one page only)
- Use `replace` write disposition to start
- Remove `refresh="drop_sources"` if present — `dev_mode` handles the clean slate

#### Optionally: parameterize the source function

`@dlt.source` and `@dlt.resource` are regular Python function decorators — expose useful parameters:

- **Credentials** (`dlt.secrets.value`): auto-loaded from secrets.toml, user can also pass explicitly
- **Config** (`dlt.config.value`): auto-loaded from config.toml, user can also pass explicitly
- **Runtime params** (plain defaults): date ranges, filters, granularity — give sensible defaults so the pipeline works out of the box

Users will call the source both ways:
```python
pipeline.run(my_source())  # auto-inject from TOML
pipeline.run(my_source(starting_at="2025-01-01T00:00:00Z", bucket_width="1h"))  # explicit
```

Add a docstring documenting parameters and example calls.

#### Example

```python
@dlt.source
def my_source(
    access_token: str = dlt.secrets.value,
    starting_at: str = None,
):
    """Load data from My API.

    Args:
        access_token: API token. Auto-loaded from secrets.toml.
        starting_at: Start of range (ISO8601). Defaults to 7 days ago.
    """
    if starting_at is None:
        starting_at = pendulum.now("UTC").subtract(days=7).start_of("day").to_iso8601_string()

    config: RESTAPIConfig = {
        "client": {"base_url": "https://api.example.com/v1/", ...},
        "resources": [...],
    }
    yield from rest_api_resources(config)
```


### 6b. Set up config and secrets TOMLs

**Essential Reading** Credentials & config resolution: `https://dlthub.com/docs/general-usage/credentials/setup.md` `https://dlthub.com/docs/general-usage/credentials/advanced`

**Config** (non-secret values like `base_url`, `api_version`): edit `.dlt/config.toml` directly.

```toml
# .dlt/config.toml
[sources.<name>]
base_url = "https://api.example.com/v1/"
```

**Secrets** (API keys, tokens, passwords): **never** read or write `secrets.toml` directly.  **Never** run commands that output secret values (e.g. `gh auth token`, `env | grep KEY`).

Use `secrets_view_redacted`, `secrets_list`, and `secrets_update_fragment` MCP tools (or equivalent `dlt ai secrets` CLI commands) — see `setup-secrets` skill for details.

Use `secrets_list` to pick the target file, then `secrets_update_fragment` with the TOML fragment:
```toml
[sources.<name>]
access_token = "ak-*******-cae"
```
- `<name>` = `name=` arg on `@dlt.source` if set; otherwise the function name
- Use meaningful placeholders that hint at format (not generic `<configure me>`)

For more complex credential setup (research where to get keys, multiple providers), use `setup-secrets` skill.

**ALWAYS Get Feedback** before you run the pipeline for a first time. Show summary of files that you changed or generated.

### 7. Debug pipeline - first run
When user requests to run pipeline **ALWAYS use `debug-pipeline`** to diagnose and guide credential setup
**NEVER add more endpoints** before that - keep it simple
