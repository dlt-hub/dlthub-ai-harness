---
name: harden-workspace
description: "Use when the user wants to harden a workspace before or after a deployment: who can see production data through notebooks, dashboards and MCP servers, a strict environment, the read profile of interactive jobs, and which dependencies each job gets. Checks .dlt/.workspace, the deployment manifest and the requirements manifest, and proposes changes."
---

# Harden a workspace

Three checks: who reads production data through interactive jobs, whether the environment enforces that, and what each
deployed job installs. This skill reads first and changes nothing before the user agrees.

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/profiles.md |
https://dlthub.com/docs/hub/pipeline-operations/job-configuration.md (Dependency groups, Options of module jobs)

Two read-only commands show what a deployment would get:

```bash
uv run dlthub local info --show-manifest       # the expanded deployment manifest, as YAML; warnings on stderr
uv run dlthub local info --show-requirements   # the requirements manifest a deployment uploads, as JSON
```

## 1. Strict environments

Read `strict_access` of each environment in `.dlt/.workspace`.

- **Not strict** (the built-in `prod` of a new workspace): a job that declares read access runs with the write profile
  `prod` while `access` has no settings files. `deploy` only warns. Every viewer of a notebook, a dashboard
  or an MCP server then reads with credentials that can write.
- **Strict**: a job gets only a profile with exactly the data access it declares, and with settings files. Otherwise
  the deployment fails and names the fix.

When it is off, suggest turning it on and say why. The order matters:
1. Add the read profile first (step 2), or the next deployment fails on every interactive job.
2. Set `strict_access: true` on the environment in `.dlt/.workspace`. No command sets it on an environment that
   exists, and dlt validates the file on the next command.
3. A strict environment deploys no workspace dashboard. To keep it, set `deploy_dashboard = true` in its section:

   ```toml
   # .dlt/config.toml
   [workspace.environment.prod]
   deploy_dashboard = true
   ```

## 2. Interactive jobs and the read profile

1. In `--show-manifest`, find the interactive jobs: `entry_point.job_type` is `interactive` (notebooks, the workspace
   dashboard, MCP servers), with `access.data: [read]`. `require.profile` shows only when a job declares a profile.
   The manifest does not match jobs to profiles: `deploy` does that.
2. `uv run dlthub profile list` names the read profile of each environment (`access` in `prod`, `<env>-read`
   elsewhere). `ls .dlt/` shows whether it has settings files: `access.config.toml` or `access.secrets.toml`. Never
   open a secrets file.
3. When there are interactive jobs and the read profile has no settings files, say how to add them:
   - `uv run dlthub profile add access`: for a declared profile, dlt creates only the settings files that are missing;
   - `uv run dlthub profile add staging-read --access read --environment staging` in another environment;
   - put read-only credentials in `.dlt/access.secrets.toml` with (`setup-secrets`). (`setup-profiles`), use case 3,
     has the details;
   - make the role in the destination read-only. dlt trusts the declaration and never checks what a credential can do.
4. `dlthub profile add` shows what it changes and asks before it writes. Run it after the user agrees.

## 3. Dependencies that only this machine needs

In `--show-requirements`, the `main` group goes to every job. Packages that only local work needs go to the `dev`
group, which a deployment installs for no job unless one asks for it:

- tools: `pytest`, `ruff`, `mypy`, `ipykernel`;
- `fastmcp` for the local MCP server. An MCP server job still gets `fastmcp` from its launcher, and a notebook gets
  `marimo` from its launcher.

```bash
uv remove fastmcp && uv add --dev fastmcp
```

Before you move a package, search the job modules for its import (`Grep` for `import fastmcp`, `from fastmcp`). A
batch job must not lose a package it imports.

## 4. A group for interactive jobs

Packages that only notebooks and apps import, such as `pandas`, `plotly` or `altair`, go to a group of their own. Only
the jobs that opt in install it:

```bash
uv remove pandas plotly && uv add --group notebooks pandas plotly
```

```py
# reports/github_report.py, a marimo notebook
import marimo

__require__ = {"dependency_groups": ["notebooks"]}

app = marimo.App()
```

A function job opts in with `require={"dependency_groups": ["notebooks"]}` on its decorator, for example
`@run.interactive`. Check with `--show-manifest` that each interactive job lists the group in
`require.dependency_groups`.

## 5. Show the plan, then change

**STOP**: show every change and the files it touches, for example:

```txt
.dlt/.workspace          prod: strict_access false -> true
.dlt/config.toml         [workspace.environment.prod] deploy_dashboard = true
.dlt/access.*.toml       new, read-only credentials (placeholders)
pyproject.toml           fastmcp, pytest -> dev; pandas, plotly -> group notebooks
reports/github_report.py __require__ = {"dependency_groups": ["notebooks"]}
```

After a yes, make the changes, then run `--show-manifest` and `--show-requirements` again and show what changed. The
next deployment ships it.
