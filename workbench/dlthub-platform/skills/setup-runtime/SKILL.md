---
name: setup-runtime
description: Verify dlthub workspace is ready for dltHub Platform. Use when user wants to deploy for the first time, or when another skill reports missing prerequisites like .workspace file or dlt[hub] dependency.
---

# Verify workspace for dltHub Platform

Lightweight check that the workspace is ready for runtime work. Run through each check and fix issues as found.

**Handed over from another toolkit?** What it built is in the session already: the pipeline, its destination and dataset, the transformation scripts or the notebook. Carry them into these checks and the deployment without discovering them again.

**Reference**:
- Workspace intro (install `dlt[hub]`, create a workspace): https://dlthub.com/docs/hub/getting-started/installation.md
- Workspace setup (convert a Python project, credentials per profile): https://dlthub.com/docs/hub/pipeline-operations/workspace-setup.md

## 1. Verify Python project

Check `pyproject.toml` exists in the project root. If not:

```bash
uv init
```

dltHub Platform uses `pyproject.toml` to install dependencies remotely.

## 2. Check `.dlt/.workspace` file

```bash
ls .dlt/.workspace
```

This file enables profiles and the runtime CLI. If missing, use `dlthub init` (preferred):

```bash
dlthub init                    # creates .dlt/.workspace, prompts for workspace name
dlthub init --name <workspace> # skip prompt
dlthub init --dry-run          # preview only
```

Or manually as fallback: `touch .dlt/.workspace`

> **Heads up:** the workspace description shown in the dltHub Platform UI comes from the first line of the docstring in `__deployment__.py`. You can set it now or later when creating the manifest in (`prepare-deployment`).

## 3. Check `dlt[hub]` dependency

Verify `dlt` with the `hub` extra is installed:

```bash
uv pip show dlt
```

If not installed or missing the `hub` extra:

```bash
uv add "dlt[hub]"
```

If adding `dlt` to `pyproject.toml`, pin the exact installed version (`==`) — `uv add` may downgrade pre-release versions.

## 4. Login to dltHub Platform

```bash
dlthub login
```

- Opens a device-code OAuth flow (user visits URL + enters code in browser)
- After login, connect to a workspace:

```bash
dlthub workspace connect                          # interactive prompt to select or create
dlthub workspace connect <name_or_id>             # skip prompt
dlthub workspace connect <name_or_id> --org-id <id>  # specify org
```

- The selected workspace ID is stored in `config.toml` under `[runtime] workspace_id`
- To **switch workspaces** (no re-login needed): `dlthub workspace connect <name_or_id>`
- To **log out**: `dlthub logout`

## 5. Check profiles

Use `get_workspace_info` (or `dlthub profile list`) to see the declared profiles and which of them have settings files. For profiles, see the (`setup-profiles`) skill. If the settings files of `prod` are missing, (`prepare-deployment`) creates them.

Tell the user what's present and what the next step is: use (`prepare-deployment`) to set up production credentials and destinations.
