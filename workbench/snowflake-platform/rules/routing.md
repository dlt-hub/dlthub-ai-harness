# Snowflake routing

When the user's intent is about Snowflake, open the skill below directly. These routes win over `dlthub-router` for
Snowflake intents. The skills are already in this workspace: install nothing.

```
intent                                                                  → skill
deploy, run or schedule jobs on Snowflake; "move my pipeline to prod"   → setup-snowflake-workspace (workflow entry)
where the jobs load: the prod destination, another database or role    → setup-snowflake-data-connection
a job failed on Snowflake; job runs, logs, pause, resume, cancel        → maintain-snowflake-jobs
a second deployment: ci, staging, a test schema                         → manage-snowflake-environments
the dltHub organization, remote workspaces, the app status page        → connect-dlthub-control-plane
install or upgrade the runner in an account, grant a role (admin)       → install-snowflake-runner
what Snowflake already knows about a topic: data, definitions, usage    → collect-snowflake-context
a semantic view on the model; Cortex Analyst or an agent on the CDM     → create-snowflake-semantic-view
Snowflake credentials, naming, types, load errors, tables of other tools → setup-snowflake-destination
a Cortex agent writes comments and a semantic view after each load     → annotate-with-cortex
```

- A new pipeline or model still starts in its own toolkit (`find-source`, `annotate-sources`). The
  `Business and semantic context on Snowflake` rule says where `collect-snowflake-context` joins them.
- Snowflake objects that dlthub did not create (other tasks, streams, dynamic tables) are not ours: use the
  bundled Cortex Code skills for them.
