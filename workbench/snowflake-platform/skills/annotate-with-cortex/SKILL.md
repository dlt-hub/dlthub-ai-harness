---
name: annotate-with-cortex
description: Add a Snowflake Cortex agent step to a dlt pipeline that loads into Snowflake, so that the data gets column and table comments grounded in the actual rows and a semantic view with metrics, dimensions and synonyms, with no human in a chat window. Use this whenever someone with a dlt pipeline on Snowflake asks to annotate, describe, document or comment their loaded tables, to add semantic context or a semantic view or Cortex Analyst model on top of dlt data, to "let CoCo / Cortex / an agent write the descriptions", to run the hand-off from the dltHub AI harness ontology to Snowflake as a job, or to automate what they did by hand in CoCo in Snowsight. Also use it when a dlt job should call the Cortex Agents REST API (agent:run) for anything that reads the warehouse and proposes SQL, even if the words "semantic view" or "comments" never come up. Do NOT use for Snowflake credentials, naming or type problems of the load itself, use setup-snowflake-destination for those.
---

# dlt + Cortex agent: annotate the loaded data and build a semantic view

## What you build

One Python module in the user's dlt project, usually `cortex_annotate.py`, with one entry point,
`annotate(pipeline, business_context)`, run by a job of its own after the load job succeeds:

1. Reads the dlt pipeline schema (tables, columns, parent/child links) so the agent is told exactly
   what exists and the job can validate what comes back.
2. Makes one call to the Cortex Agents REST API (`POST /api/v2/cortex/agent:run`) with the CoCo
   code toolset and `permission_policy: always_allow`, authenticated as the same Snowflake user dlt
   loads with. The agent profiles the tables, checks the business context against the rows, and
   answers with one JSON object: table comments, column comments, a short report, and the DDL of a
   semantic view.
3. Applies the answer with plain SQL: `COMMENT ON TABLE/COLUMN` for names the dlt schema knows,
   `CREATE OR REPLACE SEMANTIC VIEW` with one fix round if Snowflake rejects the DDL, and a small
   review table loaded with dlt that holds the agent's report.

The split matters and the user should hear it: the agent's SQL tool in the sandbox is read-only
(SELECT and SHOW), so the agent cannot write comments or views itself. The job writes, and writes
only what it can validate. That is also why the whole thing is safe to run unattended as a job.

Start from `scripts/cortex_annotate.py` in this skill. It is a working, generalised version of a
module that ran in production on dltHub.
Copy it into the project, then adapt the prompt and the wiring; do not rewrite it from scratch.

## Workflow

### 1. Find out what you are annotating

Look at the pipeline code and `.dlt/` before writing anything:

- Pipeline name, destination (`snowflake`), dataset name, and which tables land. If the pipeline
  has run locally, `pipeline.default_schema.tables` is the ground truth; nested child tables show
  up with a `parent` key and join on `_dlt_parent_id = _dlt_id`, position in `_dlt_list_idx`.
- How Snowflake credentials are configured: `destination.snowflake.credentials` with `private_key`
  (key pair) or `authenticator = "PROGRAMMATIC_ACCESS_TOKEN"` + `token` (PAT). The module reads
  them with `dlt.secrets[...]`; never read or print the secrets file. If the destination is
  named (`[destination.warehouse]` with `destination_type = "snowflake"`), change the key in
  `_credentials()` to that name. If the load itself does not work yet, go to
  `setup-snowflake-destination` first.
- Business context: rules the user already has (project docs, an ontology, metric definitions, a
  Slack message). This is what the agent cannot know from the rows: what counts as revenue, which
  rows are test data, which time zone a month is in, what the codes mean. Ask for it if there is
  none; a sentence or two is enough to start.
- How the load is deployed. The annotation is its own job that starts when the load job
  succeeds, never a call inside the load function: the load is the product and must not fail or
  slow down because Cortex is slow or down, the annotation can be re-run without reloading, and
  its logs show the agent's report on its own. Only for a quick local try is calling
  `annotate(pipeline, ...)` by hand after `pipeline.run()` acceptable, and say that it is a try.

### 2. Check the prerequisites, say them out loud

- The Snowflake role the pipeline uses needs `SNOWFLAKE.CORTEX_USER` (granted to PUBLIC by default,
  often revoked) and the usual privileges on the dataset. Creating a semantic view needs
  `CREATE SEMANTIC VIEW` on the schema.
- The account must not be a trial account; Cortex Agents are not available there.
- Dependencies: `requests`, `pyjwt`, `cryptography` (the last two only for key pair auth). Add
  them with `uv add`, pinned like the rest of the project.
- The agent call takes one to five minutes for a few tables and costs Cortex credits per run. The
  REST API times out at 15 minutes; keep the prompt scoped to the tables that matter.

### 3. Adapt the template

Copy `scripts/cortex_annotate.py` and go through the marked spots:

- `TASK`: keep the structure (profile, check the context, rewrite comments, propose the view,
  report, answer as JSON) and fill in the business context the user gave. Say what the rows cannot
  tell: definitions, exclusions, time zones, code meanings, which metrics finance wants. Name the
  metrics and dimensions you expect so the view is predictable; the agent still verifies every
  expression against the data.
- `VIEW_SUFFIX`, `REVIEW_TABLE`: naming, so the objects sit next to the dataset.
- The logical model for the view is derived from the dlt schema in `_model_hint()`: one logical
  table per dlt table, `PRIMARY KEY (_dlt_id)` for roots, `(_dlt_parent_id, _dlt_list_idx)` for
  children, and a relationship child → parent. Keep that; it is what makes the agent's DDL compile
  on the first try most of the time.
- If the project already has an ontology in the warehouse (for example `ONTOLOGY__*` tables from
  the dltHub AI harness), tell the agent to read it and keep its definitions word for word, then
  append what it observed. Definitions come from people; observations come from the data.

See `references/agent-api.md` for the request and response shapes, auth variants and the limits
you are designing around, and `references/semantic-view.md` for the DDL skeleton and the query
that proves the view answers correctly.

### 4. Wire it in as a follow-up job, with the dlthub-platform toolkit

Give the step its own entry point next to the load, for example `annotate_<source>.py` with a
`run()` that builds the same pipeline (same name, destination and dataset, so
`sync_destination()` finds the schema) and calls `annotate(pipeline, BUSINESS_CONTEXT)`. Then
declare it in `__deployment__.py` as a job that follows the load:

```python
@run.job(trigger=load_job.success, require={"static_egress_ips": True})
def annotate_job():
    """Cortex agent documents the dataset after a successful load."""
    from annotate_source import run

    run()
```

`static_egress_ips` matters when the Snowflake user sits behind a network policy, which PAT users
always do. Never put the call inside the load function: if the user's pipeline script already does
`pipeline.run(...)` and then annotates in the same process, split it.

Deployment itself is the dlthub-platform toolkit's job, so hand over to it instead of improvising:
`setup-runtime` checks the workspace and the login, `prepare-deployment` creates or extends
`__deployment__.py` and the profile config, `deploy-workspace` runs `dlthub deploy --dry-run`,
deploys and shows the logs. If those skills are not installed in the project, install the toolkit
first with `uv run dlthub --non-interactive ai toolkit install dlthub-platform`, then start with
`setup-runtime`. The deployment bundles everything `.gitignore` does not exclude; keep large
files out or the upload fails with HTTP 413.

Do not add schedules, instance sizes or timeouts to jobs on your own, and do not deploy unless the
user asked for it; those spend the user's runtime budget and are their call. Tell them what the
job is triggered by and that nothing is scheduled.

### 5. Run it once and show the evidence

Run the step against the real dataset (locally with `uv run python ...`, or trigger the job) and
look at three things before calling it done:

- The agent's report lines in the output: what it confirmed, what it changed, what it added.
  Surprises here (test rows, time-zone shifts, codes with no meaning) are the value of the step.
- `SELECT column_name, comment FROM <db>.INFORMATION_SCHEMA.COLUMNS WHERE table_schema = ...` to
  see the comments landed and read as "definition, then Observed: facts".
- A `SELECT * FROM SEMANTIC_VIEW(<view> METRICS ... DIMENSIONS ...)` query next to a hand-written
  ground truth query for the same number. They must agree; if not, read the agent's expression and
  the business context again, one of them is wrong.

If the DDL fails twice even with the fix round, read the Snowflake error: usually a column that
does not exist, a dimension on the wrong logical table (line-level columns belong to the child
table), or an expression that references a logical table name the DDL did not define.

## Things that go wrong, and why the template does what it does

- The agent answers with prose around the JSON, or inside a fence. `_parse_json` takes the text
  between the first `{` and the last `}`; keep that rather than trusting a clean answer.
- Identifiers: Snowflake upper-cases unquoted names, dlt schema names are snake_case. Compare
  upper-cased on both sides, write unquoted, and never let the agent invent a column: skip any
  comment for a column the dlt schema does not have.
- `TIMESTAMP_LTZ` columns and session time zones move rows across month boundaries; if the
  business context says UTC, say it in the prompt and expect `CONVERT_TIMEZONE('UTC', col)` in the
  view. Check it with the ground truth query.
- Filters belong inside the metric expressions (`SUM(IFF(status = 'C', amount, 0))`) so that any
  slice of the view respects them. Put the business rules into `AI_SQL_GENERATION` too, so that
  Cortex Analyst and CoCo explain them when they answer.
- The review table is replaced on every run and the comments are overwritten. That is intended:
  the account should never drift from the last verified state. Say so in the docs of the project.
- Never let the load's success depend on the agent: the annotation is a follow-up job, so a
  Cortex outage shows up as a failed annotation run, not as missing data.

## Reference docs

- Cortex Agents REST API: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-rest-api
- Semantic views: https://docs.snowflake.com/en/user-guide/views-semantic/overview
- `CREATE SEMANTIC VIEW`: https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view
- Key-pair authentication: https://docs.snowflake.com/en/user-guide/key-pair-auth
- dlt Snowflake destination: https://dlthub.com/docs/dlt-ecosystem/destinations/snowflake.md
- dltHub deployments and job triggers: https://dlthub.com/docs/hub/pipeline-operations/deployments.md
