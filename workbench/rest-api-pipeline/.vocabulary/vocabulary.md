# rest-api-pipeline Vocabulary

Overlay for the [base vocabulary](/.vocabulary/vocabulary.md). Terms here extend or override the base for this toolkit's context only.

## Accepted alternatives

Terms that are deprecated/flagged globally but acceptable in this toolkit because users work directly with REST API endpoints.

| Global term | Accepted here as | Reason |
|-------------|-----------------|--------|
| resource | endpoint | In REST API context, each resource wraps a single API endpoint. Users discover and refer to data by endpoint path, not by dlt resource name. |

## Deprecated terms

Terms previously used in this toolkit that have been removed. Flag if found in skills.

| Term | Alternatives | Was | Reason |
|------|-------------|-----|--------|
| docs.yaml | docs yaml, scaffold yaml | Auto-generated YAML file with API endpoint scaffolding created by `dlt init` | No longer generated; endpoint config is inline in pipeline code |

## Toolkit-specific terms

Terms used in this toolkit's skills that are not in the base glossary.

| Term | Alternatives | Definition |
|------|-------------|-----------|
| RESTAPIConfig | rest_api config, config dict | Declarative Python dict configuring the `rest_api` source: client settings, auth, and resource list. |
| data_selector | data selector, json_path | JSONPath expression pointing to the data array in an API response (e.g., `"data"`, `"results.items"`). When omitted, dlt auto-detects. |
| paginator | pagination config | Pagination strategy for a resource. Can be auto-detected or explicit (`OffsetPaginator`, `PageNumberPaginator`, `JSONResponseCursorPaginator`, `HeaderLinkPaginator`). |
| base_url | base URL | Root URL for all API requests in a `RESTAPIConfig` client (e.g., `https://api.example.com/v1/`). |
| auth | authentication, auth config | Authentication configuration in RESTAPIConfig client. Supports `BearerTokenAuth`, `APIKeyAuth`, `HttpBasicAuth`, `OAuth2ClientCredentials`, and custom auth classes. |
| processing_steps | processing steps | List of `map`, `filter`, or `yield_map` transforms applied to data items during extract, before normalization. Configured per resource. |
| add_limit | .add_limit(), page limit | Development helper that caps the number of pages fetched per resource. Prevents runaway pagination during debugging. |
| dev_mode | dev mode, development mode | Pipeline mode (`dev_mode=True`) that creates a fresh dataset on every run. Used during pipeline development. |
| verified source | verified dlt source | Pre-built, maintained dlt source distributed via `dlt init <source> <destination>`. Preferred over building from scratch when available. |
| core source | built-in source | Source distributed with the dlt package (`rest_api`, `sql_database`, `filesystem`). Available without additional installation. |
