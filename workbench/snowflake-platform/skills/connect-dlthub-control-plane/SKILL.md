---
name: connect-dlthub-control-plane
description: Explain and check how a Snowflake workspace is linked to the dltHub control plane through the dltHub app. Shows the dltHub organization, the remote workspaces of the environments, the status page of the app and the metadata sharing levels, and what the current mock app does not do yet. Use when the user asks about the dltHub organization, remote workspaces, workspace ids, what dltHub sees of their account, or the status page. Do NOT use to deploy (`deploy-snowflake-workspace`).
argument-hint: "[environment]"
---

# The dltHub control plane

The dltHub app is a Snowflake Native App. It is the link between a Snowflake account and a dltHub organization: the
jobs and the commands talk to the app, and the app talks to the control plane. Snowflake roles decide who may use
it. Your data never leaves Snowflake through it.

**Reference**: `apps/dlthub_app/README.md` (the trusted link, the metadata sharing levels, the roles) ·
`docs/ARCHITECTURE.md` § The dltHub app

## 1. Show the link of this workspace

```sh
uv run dlthub snowflake info
```

The **dltHub** section shows:
- **Organization** and **Organization ID**: the dltHub organization that the app is connected to.
- **Remote workspace** and **Remote workspace ID**: the remote workspace of this environment. Each environment of a
  workspace is a remote workspace of its own: `github_actions` for `prod`, `github_actions-ci` for `ci`.
- **dltHub app**: the name of the app in the account.

The ids are in `.dlt/config.toml` after the first deploy (`[runtime] organization_id`,
`[workspace.environment.<env>] workspace_id`). Committed, they keep CI and other users on the same remote workspace.

## 2. Show the status page

In Snowsight, open the app (`DLTHUB_APP`) under the apps of the account. Its status page shows whether the app is
connected, the organization, and the connected remote workspaces with their environment, the last job run and the
job runs of the last 7 days. Roles with the application roles `ADMIN` or `WORKSPACE_DEPLOYER` can open it. Snowsight
asks for a warehouse to run it.

## 3. Explain what is shared

Tell the user the metadata sharing level of the app, from `apps/dlthub_app/README.md` § Metadata sharing levels.
Each level adds to the one before it: only Snowflake, the jobs control plane, traces, logs, code and configs. User
data is never shared.

## 4. Say what the app does not do yet

This version of the app is a **mock**:
- it works on the **Only Snowflake** level, without a real trusted link;
- it is connected to a placeholder organization and keeps the job runs in this account only;
- a job run gets no interval, so a job that declares `freshness` does not run;
- the run authorization is not signed, and the app sends no billing events.

Do not log in to the dltHub platform to work around it, and do not promise features of a later version.
