---
name: add-pipeline-mcp
description: Set up a dlt pipeline MCP server so the agent can query schemas and data. Use after a pipeline has been loaded successfully and you need to inspect data programmatically.
argument-hint: <pipeline-name>
---

# Set up dlt pipeline MCP server

Configure a dlt pipeline MCP server so the agent can query loaded data via SQL, inspect schemas, and explore tables.

Parse `$ARGUMENTS`:
- `pipeline-name` (required): the dlt pipeline name (e.g., `anthropic_usage_pipeline`)

## Steps

### 1. Verify the pipeline exists and has data

```
dlt pipeline <pipeline_name> info
```

If the pipeline doesn't exist or has no loaded packages, stop and tell the user to run the pipeline first (`debug-pipeline`).

### 2. Find the .mcp.json location

The `.mcp.json` must be placed in the **same directory that contains the `.claude` symlink/folder** — that's the Claude Code project root.

Find it:
```
ls -la .claude  # check if symlink — the directory containing it is the project root
```

### 3. Add MCP server to .mcp.json

Read the existing `.mcp.json` at the project root (create if it doesn't exist). Add the dlt pipeline MCP server entry.

The `.mcp.json` is shared with other developers — do NOT use hardcoded absolute paths.

```json
{
  "mcpServers": {
    "dlt-pipeline-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "dlt", "pipeline", "<pipeline_name>", "mcp", "--stdio"]
    }
  }
}
```

**Key points:**
- Claude Code launches MCP servers from the project root (where `.mcp.json` lives)
- `uv run` finds the venv relative to cwd — make sure `pyproject.toml` is at the project root
- `--stdio` transport is required for Claude Code
- One MCP server per pipeline — if the project has multiple pipelines, add multiple entries with different names

**Multiple pipelines example:**
```json
{
  "mcpServers": {
    "usage-pipeline": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "dlt", "pipeline", "anthropic_usage_pipeline", "mcp", "--stdio"]
    },
    "shopify-pipeline": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "dlt", "pipeline", "shopify_store_pipeline", "mcp", "--stdio"]
    }
  }
}
```

### 4. Inform the user

The MCP server will be available after Claude Code restarts (or on next session). Tell the user:

```
MCP server configured for pipeline: <pipeline_name>

Available tools after restart:
- available_tables: list all tables in the pipeline
- table_schema: get column names, types, constraints for a table
- table_head: first 10 rows of a table
- query_sql: run SQL queries against loaded data
- bookmark_sql: save query results for later use
- read_result_from_bookmark: retrieve saved results

Restart Claude Code to activate.
```
