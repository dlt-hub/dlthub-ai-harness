---
name: install-snowflake-runner
description: Install or upgrade the SPCS Context Runner in a Snowflake account and give roles access, for the account admin. Installs the dltHub app, the compute pool and warehouse of the jobs, the image repository and the default external access integration, then grants roles that deploy workspaces. Use when an admin wants to set up or upgrade the runner, grant a role, or uninstall it, or when a user's `dlthub snowflake` command says the app or a grant is missing. Do NOT use to set up a user's workspace (`setup-snowflake-workspace`).
argument-hint: "[admin-connection] [database] [role]"
---

# Install the SPCS Context Runner (admin)

An account admin does this once per account, and once per role that deploys workspaces. Users cannot do it for
themselves: their errors point here.

**Reference**: `admin/README.md` (what the install creates, what a grant gives a role) · `README.md` § Getting
started, steps 1–2 · `uv run python admin/install.py --help`

## 1. Check who runs it and where

- The admin works in a clone of this repository, with `uv`, docker and the Snowflake CLI.
- If the user is not an admin, stop. Write them the message for their admin from `setup-snowflake-workspace`
  step 6.

## 2. Pick the admin connection, the database and the names

Ask the admin for:
- `CONNECTION`: their Snowflake connection. Its role owns the app. `ACCOUNTADMIN` has every privilege that the install
  needs: `CREATE APPLICATION PACKAGE`, `CREATE APPLICATION`, `MANAGE APPLICATION SPECIFICATIONS`, and the privileges
  to create a compute pool, a warehouse and an integration. Test it with `snow connection test -c <admin>` (it shows
  the role, never the key; do not read `connections.toml`).
- `DATABASE`: the database of the workspaces, for example `ANALYTICS`. The shared schema `DLTHUB_SHARED` goes there.
  Empty means the database of the connection.
- Other names than the defaults (`DLTHUB_APP`, `DLTHUB_JOBS_POOL`, `DLTHUB_JOBS_WH`,
  `DLTHUB_DEFAULT_WORKSPACE_ACCESS`): only when the account has rules for names. They need
  `uv run python admin/install.py` with the options of `--help`, and every user must then set them in
  `[snowflake.deploy]`.

## 3. Dry run

```sh
make install-app CONNECTION=admin DATABASE=ANALYTICS DRY_RUN=1
```

It runs nothing and writes the SQL. Summarize it for the admin: the app and its version, the pool and warehouse
(created suspended), the shared schema and image repository, the integration, and the network access that the app
asks for.

**STOP**: the install creates account-level objects. Get an explicit yes.

## 4. Install or upgrade

```sh
make install-app CONNECTION=admin DATABASE=ANALYTICS
```

- It builds the base image with docker and pushes it, so it takes some minutes.
- It approves the network access of the app.
- A second run upgrades the app and keeps its state. That is also how to upgrade later.

When it fails, the message says what is missing. Grant it or switch to a role that has it, then run again.

## 5. Give a role access

The grant goes to a role, not a user. Deploy creates the Snowflake tasks as this role and the jobs run as it.

```sh
make grant-role CONNECTION=admin DATABASE=ANALYTICS ROLE=DATA_ENGINEER DRY_RUN=1
make grant-role CONNECTION=admin DATABASE=ANALYTICS ROLE=DATA_ENGINEER
```

- `ROLE` takes several roles, separated by spaces.
- `admin/README.md` § What a grant gives a role lists the privileges.
- To let a person deploy, grant them the role: `GRANT ROLE DATA_ENGINEER TO USER JANE;`.

**STOP** before each grant: show the dry run and get a yes.

## 6. Check and hand over

- In Snowsight, the admin opens the app `DLTHUB_APP`: its status page shows the organization and the connected
  workspaces. There are none before the first deploy.
- Tell the admin what to send to the users: the role, the database, and any names that are not the defaults. The
  users then run (`setup-snowflake-workspace`).

## Uninstall and wipe

Only when the admin asks for it, and after a dry run (`DRY_RUN=1`) and an explicit yes:

```sh
make uninstall-app CONNECTION=admin   # drops the app; the shared objects, the pool and the warehouse stay
make wipe-app CONNECTION=admin        # also drops the pool and the warehouse, after the admin types the name
```

Both list what they dropped and what they did not find. The wipe leaves a pool or a warehouse that does not
carry the dltHub markers of the install, and says so before it asks. The workspace schemas stay: the roles of
the users own them.
