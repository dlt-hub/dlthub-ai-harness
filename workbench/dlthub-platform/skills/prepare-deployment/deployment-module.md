# Creating `__deployment__.py`

The deployment module declares what exists in the workspace. Runtime discovers
jobs by inspecting its contents when you run `dlthub deploy`.

## Minimal example

```python
"""My workspace -- ingest and transform customer data"""

from my_pipeline import ingest_data
from my_transforms import run_transforms
import my_notebook

__all__ = ["ingest_data", "run_transforms", "my_notebook"]
```

## Import rules

- **Function imports** (`from my_pipeline import ingest_data`) produce one job
  per function. The function must be decorated with `@run.job`, `@run.pipeline`,
  or `@run.interactive`.
- **Module imports** (`import my_notebook`) produce one job per module. The
  framework is auto-detected:
  - `marimo.App` -> interactive notebook
  - `FastMCP` instance -> MCP tool server
  - `streamlit` usage -> interactive dashboard
  - Plain module with `if __name__ == "__main__"` -> batch job

## Required elements

| Element | Purpose |
|---------|---------|
| `__all__` | Explicit list of names to deploy. Strongly recommended -- without it the manifest generator scans the full `__dict__` and warns. |
| `__doc__` (module docstring) | First non-empty line becomes the workspace description in the Runtime dashboard. |

## Job references (`job_ref`)

Every job gets a reference in `jobs.<section>.<name>` form:

| Import style | job_ref | Example |
|-------------|---------|---------|
| `from my_pipeline import ingest_data` | `jobs.my_pipeline.ingest_data` | Function: section=module, name=function |
| `import my_notebook` | `jobs.my_notebook` | Module: section=module name |

**Job names**: bare names work when unambiguous. `dlthub run ingest_data` resolves to `jobs.my_pipeline.ingest_data` if there's only one `ingest_data` in the workspace.

## Verify and debug

```bash
dlthub deploy --dry-run              # preview what would change
dlthub deploy --show-manifest        # dump full manifest as YAML
```

## Defining jobs inline

You can define decorated jobs directly in `__deployment__.py`. Use `section=`
to give the job a clean config section:

```python
from dlt.hub import run

@run.interactive(section="my_mcp", interface="mcp", idle_timeout="30m")
def my_mcp_server():
    from fastmcp import FastMCP
    mcp = FastMCP("tools")
    @mcp.tool
    def hello() -> str:
        return "world"
    return mcp

__all__ = ["my_mcp_server"]
```

Without `section="my_mcp"`, the config section defaults to `__deployment__`.
