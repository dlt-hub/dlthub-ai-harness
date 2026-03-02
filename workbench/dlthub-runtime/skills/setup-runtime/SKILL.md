---
name: setup-runtime
description: Verify dlt workspace is ready for dltHub Runtime. Use when user wants to deploy for the first time, or when another skill reports missing prerequisites like .workspace file or dlt[hub] dependency.
---

# Verify workspace for dltHub Runtime

Lightweight check that the workspace is ready for runtime work. Run through each check and fix issues as found.

**Reference**: https://dlthub.com/docs/hub/command-line-interface.md

## 1. Verify Python project

Check `pyproject.toml` exists in the project root. If not:

```bash
uv init
```

Runtime uses `pyproject.toml` to install dependencies remotely.

## 2. Check `.dlt/.workspace` file

```bash
ls .dlt/.workspace
```

This file enables profiles and the runtime CLI. If missing:

```bash
touch .dlt/.workspace
```

## 3. Check `dlt[hub]` dependency

Verify `dlt` with the `hub` extra is installed:

```bash
uv pip show dlt
```

If not installed or missing the `hub` extra:

```bash
uv add "dlt[workspace,hub]"
```

If adding `dlt` to `pyproject.toml`, pin the exact installed version (`==`) — `uv add` may downgrade pre-release versions.

## 4. Login to dltHub Runtime

```bash
dlt runtime login
```

- Opens a device-code OAuth flow (user visits URL + enters code in browser)
- After auth, CLI prompts to select or create a remote workspace (interactive — needs piped input if non-interactive: `printf '1\n' | dlt runtime login`)
- Creating a new workspace requires three inputs: selection (`0`), name, description (can be empty)
- The selected workspace ID is stored in `config.toml` under `[runtime] workspace_id`
- To **switch workspaces**: `dlt runtime logout`, remove `workspace_id` from `config.toml`, then `dlt runtime login` again

## 5. Verify profile files exist

```bash
ls .dlt/*.toml
```

List existing config and secrets files. At minimum these should exist:
- `.dlt/config.toml`
- `.dlt/secrets.toml`
- `.dlt/.workspace`

Profile-scoped files (`dev.*`, `prod.*`, `access.*`) may or may not exist yet — that's fine, (`prepare-deployment`) handles their creation.

Tell the user what's present and what the next step is: use (`prepare-deployment`) to set up production credentials and destinations.
