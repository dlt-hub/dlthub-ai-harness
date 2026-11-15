---
name: collect-snowflake-context
description: Collect what the Snowflake account already knows about what the user wants to build, before any pipeline or model code. Captures the intention and the questions the result must answer, asks Cortex Sense and Business Ontology, finds existing copies of the data and how people query them (ACCOUNT_USAGE), finds the gaps, and writes the business context document `.dlthub/ontology/<slug>/context.md`. Use when `find-source` or `annotate-sources` builds context on a Snowflake account (the `Business and semantic context on Snowflake` rule), or when the user asks what Snowflake already knows about a topic. Read only.
argument-hint: "[intent] [slug]"
---

# Collect the Snowflake context

Snowflake may already know a lot about the user's topic: governed terms in Business Ontology, curated Cortex Sense
contexts, tables that hold the same data, and the queries people run on them. This skill collects that **before** any
code, so the new pipeline or model reuses names, definitions and data that exist, and brings what is missing.

It writes one document, `.dlthub/ontology/<slug>/context.md`. Then it returns to the skill that called it
(`find-source` or `annotate-sources`).

**Reference**: the bundled Cortex Code skills `$cortex-sense` (its `reference/CONTEXT_LOOKUP.md`) and
`$business-ontology` · https://docs.snowflake.com/en/sql-reference/account-usage/access_history

**Rules**
- **Read only.** Never create or change Business Ontology terms, Cortex Sense contexts, comments or grants here.
- **Evidence only.** Every definition, join, filter or metric in the document names its source: an ontology term, a
  Cortex Sense document, or real queries (how many runs, how many users). Never invent business logic.
- **Business in the document.** No credentials, roles, warehouses or row counts in `context.md`. Tell the user those
  in the chat.
- Short bullets and simple English.

## 1. Understand what the user wants to build

This step decides every later step. A wrong intention gives the wrong questions to the user, the wrong lookups and
the wrong data. Take it from the user's prompt and `$ARGUMENTS`, from the use case in the project `README.md`, or from
an existing `.dlthub/ontology/*/context.md` on the same topic. Write down:

- **What is built**: an ingestion of a source, a model (CDM) of loaded data, a semantic view, an agent, a report.
- **Who uses the result, and how**: an analyst in a dashboard, Cortex Analyst or a Snowflake Intelligence agent
  that answers questions, another pipeline, an export.
- **The questions that will be asked at the end**: 3–5 questions in the user's own words. These are the test of the
  whole work: the semantic view and the validation checks come from them.
- **The terms and metrics in those questions**, for example "active customer", "net revenue", "CI waste".
- **What matters most**: a definition that must match the finance team, full history, freshness (hourly, daily),
  the grain (per order, per day), a time range.

Example. The user says: "I want to know how much we spend on GitHub Actions every day and how much of it is waste."

```txt
built:      an ingestion of the GitHub Actions API into Snowflake, then a model
used by:    the platform team, in a daily dashboard and through Cortex Analyst
questions:  1. What did CI cost yesterday, per repository?
            2. Which share of CI minutes was waste last month?
            3. Which workflows waste the most?
terms:      daily spend, CI minutes, waste (failed and cancelled runs?), cost of a job
matters:    the definition of waste; history for 12 months; daily freshness
```

Ask the user **once, in one message**, only for what is missing or unclear. Typical gaps: the questions at the end,
and the definition of a term the user takes for granted ("waste"). Do not ask about tables, schemas or tools: the next
steps find them.

Then derive and show in one or two lines:
- `topic` (GitHub Actions CI costs), `terms`, `entities` (workflow runs, jobs, runners), `questions`;
- `slug`: a short id, for example `ci_costs`. Reuse the slug of an existing document on the topic. When this runs from
  `annotate-sources`, the slug is its CDM folder name.

## 2. Check what this session can see

```sql
SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE();
```

Then check the three sources. A failure only means that source is out: note it and go on.
- **Business Ontology**: `SELECT SYSTEM$GET_GLOSSARY_TERM_LIST('', 'TERM');` (private preview; not enabled gives
  an error).
- **Cortex Sense**: the `cortex_sense` tool when Cortex Code has it, else the SQL function of step 3.
- **ACCOUNT_USAGE**: `SELECT MAX(query_start_time) FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY;`. It needs
  `IMPORTED PRIVILEGES` on the `SNOWFLAKE` database, or the database roles `GOVERNANCE_VIEWER` and `OBJECT_VIEWER`.
  It is about 45 min behind (`ACCESS_HISTORY` up to 3 h), so very new tables show no usage yet. A `NULL` result
  means `ACCESS_HISTORY` is empty for this role or edition: then `QUERY_HISTORY` is the source of usage, as
  [evidence-sql.md](evidence-sql.md) says.

When no source is available, say so, write only the intention and the gaps (steps 6–7) and return.

## 3. Ask Business Ontology and Cortex Sense

Look up **each question and each term** of step 1, not the topic only. Run both lookups for each:

1. **Business Ontology**: filter the terms of `SYSTEM$GET_GLOSSARY_TERM_LIST('', 'TERM')` by name and synonyms,
   case-insensitive. Keep the name, domain, description, formula and synonyms.
2. **Cortex Sense**: the `cortex_sense` tool with `query` and `max_results` 5–10, or the SQL fallback:

   ```sql
   SELECT SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT($${"request_structured": {
     "query": "Which share of CI minutes was waste last month?",
     "max_results": 10,
     "results_per_type": {"table_entity": 5, "qbe": 5, "ontology_node": 5}}}$$);
   ```

   The result has `documents` (`table_entity`, `ontology_node`, `qbe`, `datamart`) and `corrections`. A missing
   or `null` `documents` means no result: `list-contexts` shows whether the account has any context at all. For wrong-account results and other details, follow `$cortex-sense`
   `reference/CONTEXT_LOOKUP.md`.

Keep what fits the topic: the definitions, the tables (`table_entity`), the example queries (`qbe`) and every
**correction**. Corrections are standing rules of the team ("exclude test accounts"): they go into the document as
they are.

## 4. Find existing data

Look for tables that already hold the data, so the user does not load it twice. Read
[evidence-sql.md](evidence-sql.md) now: section "Existing copies" has the SQL.

1. Search by the terms: `cortex search object "<term>" --types=table,view,semantic-view` for each term.
2. Search by name: the tables that the new pipeline will create (the dlt resource names from `find-source`, upper
   case) in `ACCOUNT_USAGE.TABLES`.
3. Count the reads of each match in the last 30 days, and give each planned table a verdict:
   - **CLEAR**: no copy outside the target schema;
   - **WARN**: copies exist, read 50 times or fewer;
   - **CONFLICT**: a copy outside the target is read more than 50 times: others already use this data.

**STOP on WARN or CONFLICT.** Show the copies, their schema and their reads, and ask: reuse the existing table,
load anyway, or load something else. Write the answer into the document.

## 5. Learn from how people query the data

Pick the **seed tables**: the existing tables that overlap most with the questions (most reads first, at most 3).
Confirm them with the user. Skip the tables that Cortex Sense already described with a `table_entity`.

For each seed table, collect the usage evidence of the last 60 days with the SQL in [evidence-sql.md](evidence-sql.md),
section "Usage evidence": the columns, which columns are read, which tables are queried with it, the most frequent
query shapes and the downstream views. Leave out your own queries.

From the evidence, write for each seed table:
- **grain**: one row per what;
- **joins**: to which table, on which keys, as seen in real queries;
- **required filters**: predicates that almost every query applies (`status <> 'test'`);
- **metrics**: the aggregates people compute, and how;
- **terminology**: business words and the columns they map to;
- **caveats**: identifier traps (a key joined to a differently named column), columns nobody reads;
- **example queries (QBE)**: real query shapes as a question and cleaned SQL. Match them to the questions of step 1.

Each item cites its evidence: "in 41 of 52 queries, by 6 users".

## 6. Find the gaps

For each question of step 1: **definition → data → query**. What exists, and what is missing?

- **Everything exists** (a definition, data, a query that answers it): tell the user the question can be answered
  now, for example with the existing table or semantic view. Ask whether new work is still needed. Stop unless they
  say yes.
- Otherwise derive **the data the new work must bring**, in business terms with the source's field names:
  - the entities and the fields every definition uses;
  - the history the questions need (all attempts or versions, how long records still change);
  - what identifies one record, and "the same thing" across sources (natural keys);
  - reference data that the source does not have (price lists, rates), and where the team keeps it.
- Write **validation checks**: numbered, testable statements on the loaded data ("every workflow run has a
  repository", "cost is never negative").
- Write **open questions**: terms and edge cases that no source defines. Ask the user only the ones that block the
  next step; keep the others for modeling.

## 7. Write the document

Write `.dlthub/ontology/<slug>/context.md`. Show it to the user in short form and get a yes:

```markdown
# <topic>: business context

## Intention
What is built, who uses it and how, what matters most.

## Questions
1. ... (the questions of step 1; the semantic view is tested against them)

## Business Ontology
- <term> (<domain>): <definition>. Formula: ... Synonyms: ...

## Cortex Sense
- <table or concept>: <what the context says> (<document type>)
- Corrections: <rule>, as stated by the team

## Existing data
- <DB.SCHEMA.TABLE>: <what it holds>, verdict <CLEAR|WARN|CONFLICT>, decision: <reuse | load anyway | ...>

## Table context
### <DB.SCHEMA.TABLE>
- Grain, joins, required filters, metrics, terminology, caveats, each with its evidence
- QBE: "<question>" -> <cleaned SQL>

## Data the new work must bring
## Validation checks
## Open questions

## How to collect again
The questions and terms that were looked up, the seed tables, the date of the collection.
```

## 8. Return to the calling skill

- From **`find-source`**: go on with its step 1. Carry the entities, fields and history of "Data the new work must
  bring" into the search. Use the slug as the CDM folder name later.
- From **`annotate-sources`**: go on with its step 4. Use the Business Ontology names for the concepts in
  `taxonomy.json`, and the questions as its use cases.
- When the user asked directly: summarize what Snowflake knows and what is missing, and propose the next step.
