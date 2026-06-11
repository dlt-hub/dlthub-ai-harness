---
name: new-endpoint
description: Add a new REST API endpoint/resource to an existing dlt pipeline. Use when the user wants to pull additional data from an API that already has a working pipeline.
argument-hint: "[endpoint-description]"
---

# Add an endpoint to an existing pipeline

Add a new resource to an existing dlt REST API pipeline source.

Parse `$ARGUMENTS`:
- `endpoint-description` (required): what data the user wants to add (e.g., "claude code analytics", "user profiles", "transactions")

## Steps

### 1. Read the existing pipeline

Read the pipeline `.py` file to understand:
- The `@dlt.source` function and its parameters
- The `RESTAPIConfig`: client setup (base_url, auth, paginator)
- Existing resources: names, endpoints, params, processing_steps
- How `__main__` runs the pipeline (dev_mode, add_limit, with_resources)

Note what patterns the existing resources use:
- Write disposition (`replace`, `merge`, `append`)
- Pagination style
- Incremental loading (if any)
- Processing steps (if any)
- Column type hints (if any)

### 2. Research the new endpoint

**If a docs.yaml scaffold exists**, read it for endpoint details.

**Web search** the API documentation for the new endpoint:
- Endpoint path, HTTP method
- Query parameters (required and optional)
- Response structure (nested objects, arrays)
- Pagination (same as existing endpoints or different?)
- Any special headers or auth requirements
- **Rate limits**: requests-per-second or per-minute limits for this endpoint (may differ from other endpoints)

**Read dlt docs** if you need to refresh on config options:
- REST API source: `https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic.md`
- Resource config: `https://dlthub.com/docs/general-usage/resource.md`

### 3. Choose the implementation approach

#### A. Declarative (RESTAPIConfig resource) — default

If the endpoint fits the existing client config (base_url, auth, paginator), add it to the `"resources"` list in `RESTAPIConfig`. Key decisions:

- **Endpoint path**: may differ from existing endpoints
- **Params**: handle format conversions if needed (e.g., ISO8601 → YYYY-MM-DD)
- **data_selector**: match the response structure
- **Pagination**: inherits from `client.paginator` — override per-resource if different
- **processing_steps**: add `map`/`filter`/`yield_map` if needed (e.g., `Decimal` for money — NEVER `float`)

##### Prevent optional endpoints from failing the pipeline with `response_actions`

```python
{
    "name": "org_members",
    "endpoint": {
        "path": "orgs/{org}/members",
        "response_actions": [
            {"status_code": 404, "action": "ignore"},          # org has no members — skip silently
            {"content": "Not Found", "action": "ignore"},      # match response body substring
            {"status_code": 200, "content": "error", "action": "ignore"},  # AND condition
            set_encoding,                                       # callable — applied to every response
        ],
    },
}
```

Use `"ignore"` for optional endpoints that return 404 for some parent items (e.g. repos with no issues). Use a callable to fix encoding, add/remove fields, or patch malformed responses before dlt parses them. **Never write a `processing_steps` workaround for something `response_actions` handles.** Ref: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced.md

##### Fetch child resources concurrently with `parallelized`

```python
{
    "resources": [
        "posts",
        {
            "name": "post_comments",
            "parallelized": True,          # fetch comments for all posts concurrently
            "endpoint": {
                "path": "posts/{resources.posts.id}/comments",
            },
        },
    ],
}
```

Use when the resource is a child of another (transformer pattern) and each parent has many independent child records. **Caveat**: all child pages for one parent are buffered in memory before yielding — avoid for parents with very large child sets. Ref: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced.md

#### B. Custom @dlt.resource — when declarative doesn't fit

Some endpoints can't be described in `RESTAPIConfig`:
- **Date-iterated endpoints**: API returns data for a single date, you need to loop over a range
- **Non-standard pagination** or **complex request logic**

Define a custom `@dlt.resource` inside the `@dlt.source` function. Use `RESTClient` (from `dlt.sources.helpers.rest_client`) for HTTP calls with built-in auth and pagination. Loop over dates (or other dimensions) in the resource, call `client.paginate()` for each, and yield the data. The source then yields both `rest_api_resources(config)` and the custom resource.

Read dlt docs on `RESTClient`: `https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced.md`

Update the source docstring to list the new resource and show `with_resources()` examples.

### 4. Debug pipeline

#### Test the new endpoint in isolation

Use `debug-pipeline` after each run to inspect traces and load packages.

Use `with_resources()` to load only the new resource:

```python
source = my_source()
pipeline.run(source.with_resources("new_resource").add_limit(1))
```

Temporarily edit `__main__` or run from a Python shell. This avoids re-loading all existing resources while iterating.

Run the pipeline:
```
uv run python <source>_pipeline.py
```

#### Debug pagination

Iterate over the resource directly without loading to destination:
```python
for item in source.resources["my_resource"]:
    print(item)
```

Now **Use** `debug-pipeline` skill with the tricks above!


### 5. Review consistency with existing resources

Check if the existing pipeline uses patterns that the new resource should also adopt:

- **Incremental loading**: do existing resources use `incremental` config? Should the new one too?
- **Write disposition**: is `merge` used with `primary_key`? Should the new resource also merge?
- **Processing steps**: are there shared transformations (e.g., Decimal conversion for money fields)?
- **Column hints**: do existing resources define `columns` for nullable fields?
- **Rate limits**: does this endpoint have tighter rate limits than existing ones? If so, check `.dlt/config.toml` `[runtime]` retry settings — dlt handles 429 automatically but defaults (5 retries, 60s timeout) may need tuning. See `adjust-endpoint` for the config block.

Flag any gaps to the user — the new resource works now but may need these patterns for production use.

After adding, use `validate-data` to verify schema and data look correct.


### 6. Report

```
Endpoint added: <resource_name>
- Path: <endpoint_path>
- Tables created: <list of tables including child tables>

Load with:
  source.with_resources("<resource_name>")  # just this endpoint
  source                                     # all endpoints

Available resources: <list all resource names>
```
