---
name: setup-runtime
description: "Use when the dltHub platform needs its setup before a deployment: log in to dltHub, connect or switch the remote workspace, or a skill reports a missing dlt[hub] dependency. Checks the dlt[hub] dependency, the dltHub login and the remote workspace."
---

# Set up the dltHub runtime

(`prepare-deployment`) checked first that the workspace is ready for a deployment: the jobs, their triggers, a local
debug run of each job and the `prod` profile. This skill adds what the dltHub platform needs.

**Handed over from another toolkit?** What it built is in the session already: the pipeline, its destination and dataset, the transformation scripts or the notebook. Carry them into these checks and the deployment without discovering them again.

**Reference**:
- Workspace intro (install `dlt[hub]`, create a workspace): https://dlthub.com/docs/hub/getting-started/installation.md
- Workspace setup (convert a Python project, credentials per profile): https://dlthub.com/docs/hub/pipeline-operations/workspace-setup.md

## 1. Check `dlt[hub]` dependency

Verify `dlt` with the `hub` extra is installed:

```bash
uv pip show dlt
```

If not installed or missing the `hub` extra:

```bash
uv add "dlt[hub]"
```

If adding `dlt` to `pyproject.toml`, pin the exact installed version (`==`) — `uv add` may downgrade pre-release versions.

## 2. Login to dltHub Platform

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

## Next

Deploy and run the jobs with (`deploy-workspace`).
