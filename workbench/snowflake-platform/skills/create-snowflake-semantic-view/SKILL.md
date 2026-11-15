---
name: create-snowflake-semantic-view
description: Create and maintain a Snowflake semantic view (CREATE SEMANTIC VIEW) on a CDM that dlt transformations loaded into Snowflake, from the taxonomy, the ontology, the CDM and the business context. Cortex Analyst, Snowflake Intelligence and agents then answer the user's questions in plain English. Use after `create-transformation` ran on Snowflake and the CDM tables have data, when the user wants Cortex Analyst or an agent on the model, or after the model changed. Do NOT use before the CDM exists (`annotate-sources`, `create-ontology`, `generate-cdm`, `create-transformation` first).
argument-hint: "[cdm-name]"
---

# Create a Snowflake semantic view

Render the model of one topic as one **semantic view** over the CDM tables: business names, synonyms,
relationships, facts, dimensions and metrics. Cortex Analyst uses it to turn questions into SQL.

The view adds no new meaning. Every name, synonym and description comes from the taxonomy, the ontology and Business
Ontology. Every table, key and relationship comes from the CDM. Every metric comes from the questions and
definitions in `context.md`.

**Reference**: https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view ·
https://docs.snowflake.com/en/user-guide/views-semantic/validation-rules ·
https://docs.snowflake.com/en/user-guide/views-semantic/querying

**Inputs**, in `.dlthub/ontology/<cdm-name>/`:
- `taxonomy.json`: the concepts, their synonyms (`references`) and use cases. `_name` is the CDM name and the dataset.
- `ontology.ison` and `ontology.md`: the entities, their descriptions, relationships, assumptions and semantic gaps.
- `CDM.dbml`: the tables, primary keys, refs, and measure notes (additive, non-additive).
- `context.md`, when there is one: the questions the view must answer, the Business Ontology definitions and the
  Cortex Sense corrections (`collect-snowflake-context`).

When one of the first three is missing, run the transformations skills first. The CDM must be loaded into Snowflake.

## 1. Find the target and check it

The CDM tables are in the schema of the dataset `_name`, in the database of the data connection of the
transformation job: the database of the workspace schema by default, or the `database` that
`setup-snowflake-data-connection` set. Check the tables and their rows:

```sql
SELECT table_name, row_count FROM ANALYTICS.INFORMATION_SCHEMA.TABLES
WHERE table_schema = 'SALES_MODEL' ORDER BY table_name;
SHOW GRANTS ON SCHEMA ANALYTICS.SALES_MODEL;
```

- Every CDM table must exist and have rows. Empty tables: run the transformation job on Snowflake first
  (`maintain-snowflake-jobs`).
- The role of this session needs `CREATE SEMANTIC VIEW` on the schema and `SELECT` on the tables. The role that
  loaded the data owns the schema and has both. Another role needs a grant.

Propose the name `<cdm-name>_SV` in the same schema, and confirm.

## 2. Scope: the whole ontology

Render **every entity, relationship and attribute that the CDM implements**. Do not cut the view down to the questions
you know: a view fitted to five questions fails the sixth question, whose data is in the CDM.

- Every CDM table becomes a logical table, except where the Snowflake rules force another shape. Read
  [semantic-view-rules.md](semantic-view-rules.md) now. Examples: a date dimension that several facts join becomes date
  dimensions on each fact; a hierarchy (employee → manager) becomes a second logical table; a dimension reachable by
  two paths gets a copy with a role name.
- Every CDM column except surrogate keys and lineage columns becomes a fact or a dimension.
- Leave something out only when the user chooses it. Record the choice in the DDL as a comment.

Show the list of logical tables with what each covers. **STOP** and wait for a yes.

## 3. Logical tables

For each CDM table in scope:
- **alias**: the business name of the ontology entity, plural snake case: `Order` → `orders`. A role copy gets its
  role: `employees` as `sales_reps` and `managers`.
- **PRIMARY KEY**: the surrogate key of the CDM table.
- **WITH SYNONYMS**: the `references` of the concept in `taxonomy.json`, the Business Ontology synonyms, and the
  everyday words of the ontology description: `Customer` → `'account', 'client', 'buyer'`.
- **COMMENT**: the description of the ontology entity, or the Business Ontology definition when there is one.

```sql
orders AS ANALYTICS.SALES_MODEL.FACT_ORDER PRIMARY KEY (order_sk)
  WITH SYNONYMS ('sales', 'purchases') COMMENT = 'One order placed by a customer.',
```

## 4. Relationships

One for each CDM `ref` between tables in scope, named `<from>_to_<to>`. Relationships are many-to-one or one-to-one,
onto a primary key:

```sql
orders_to_customers AS orders (customer_sk) REFERENCES customers,
sales_reps_to_managers AS sales_reps (manager_employee_sk) REFERENCES managers,
```

## 5. Facts and dimensions

From the CDM columns of each logical table:
- **Skip**: surrogate keys, `source_id`, `source_pipeline`, `_dlt_*` columns.
- **Facts**: the numeric measures (the CDM notes say additive or non-additive), and row-level values the questions
  need, for example `orders.net_amount AS orders.amount - orders.discount`.
- **Dimensions**: descriptive attributes and dates. Add the date parts that the questions use (month, quarter, year).
- Business names (no `_sk`, no source suffixes), synonyms where the questions or terms use other words, and a short
  comment for each.

```sql
FACTS (
  orders.net_amount AS orders.amount - orders.discount COMMENT = 'Order amount after discounts.'
)
DIMENSIONS (
  orders.order_month AS DATE_TRUNC('month', orders.ordered_at) COMMENT = 'Month the order was placed.',
  customers.segment AS customers.customer_segment WITH SYNONYMS ('tier')
)
```

A roll-up from the "many" side (a count of order lines on the order) must use the names you defined, not raw
columns.

## 6. Metrics

Take the metrics from the questions and definitions in `context.md` and the Business Ontology formulas. **Never
invent a metric that no question asks for.**
- A base metric goes on the table that owns the rows: `orders.revenue AS SUM(orders.net_amount)`.
- A ratio across tables is a derived metric, without a table prefix:
  `average_order_value AS orders.revenue / NULLIF(orders.order_count, 0)`.
- A snapshot measure (a balance, a stock level) uses `NON ADDITIVE BY` its date dimension.
- When a definition has two readings (revenue with or without refunds), define both with clear names, and say in the
  comment which one is the default.

## 7. Instructions for Cortex

Write `AI_SQL_GENERATION` from the ontology assumptions, the semantic gaps and the Cortex Sense corrections of
`context.md`: the currency, the fiscal calendar, sentinel rows (`UNKNOWN`, `NOT_APPLICABLE`), the default reading of
an ambiguous metric, how "this quarter" is computed. Example:

```sql
AI_SQL_GENERATION 'Amounts are in EUR. The fiscal year is the calendar year. Exclude customers with segment
''Unknown''. Revenue means net revenue after refunds unless the question says gross.'
```

Ask the user whether to add `AI_VERIFIED_QUERIES`. Warn them: Cortex then replays those queries for those questions
instead of writing SQL, so the test questions do not test the view any more.

## 8. Confirm the design

Show the logical tables, relationships, facts, dimensions and metrics, with the definition of each metric. **STOP**
and wait for an explicit yes.

## 9. Write and deploy

Write the DDL to `.dlthub/ontology/<cdm-name>/snowflake_semantic_view.sql`, next to the model it describes
(`CREATE OR REPLACE SEMANTIC VIEW ANALYTICS.SALES_MODEL.SALES_MODEL_SV ...`). The clause order is fixed:
[semantic-view-rules.md](semantic-view-rules.md).

Run it with the SQL tool of Cortex Code, or with the Snowflake CLI on the user's connection:

```sh
snow sql -c dlthub -f .dlthub/ontology/sales_model/snowflake_semantic_view.sql
snow sql -c dlthub -q "DESCRIBE SEMANTIC VIEW ANALYTICS.SALES_MODEL.SALES_MODEL_SV"
```

On an error, read the message, fix the DDL and deploy again. Record each Snowflake limitation you hit as a comment in
the DDL, so the next change keeps the workaround.

## 10. Validate against the CDM

For each question in `context.md` (or the use cases of `taxonomy.json` when there is no `context.md`):
1. Query the view: `SELECT * FROM SEMANTIC_VIEW(ANALYTICS.SALES_MODEL.SALES_MODEL_SV METRICS orders.revenue
   DIMENSIONS customers.segment WHERE orders.order_month = '2026-10-01');`
2. Answer the same question with plain SQL on the CDM tables.
3. Compare. Every answer must match.

Also run `SHOW SEMANTIC DIMENSIONS FOR METRIC <metric> IN <view>` for the metrics that the questions use. Show a
table: question | semantic view | CDM | match. A mismatch is a bug in the view or in the definition: fix it and
deploy again. To ask the questions in plain English as Cortex Analyst does, use the bundled `$query-semantic-view`
skill.

## 11. Maintain the view

Run this step when the CDM, the ontology or `context.md` changed, or when the user asks whether the view is in sync.

1. Compare the deployed view with the file:
   `SELECT GET_DDL('SEMANTIC_VIEW', 'ANALYTICS.SALES_MODEL.SALES_MODEL_SV');` against
   `.dlthub/ontology/<cdm-name>/snowflake_semantic_view.sql`.
2. Compare the file with the model: new or removed CDM tables, columns and refs; new questions or definitions in
   `context.md`.
3. Show every difference and the change you propose (steps 3–7). **STOP** for a yes, then deploy (step 9) and
   validate again (step 10).

## Output

- `.dlthub/ontology/<cdm-name>/snowflake_semantic_view.sql`: the DDL, the source of truth for the view. Commit it.
- The semantic view in Snowflake, validated against the CDM.

## Handover

- **An agent on the view**: Snowflake Intelligence talks to a Cortex agent with a Cortex Analyst tool on the view.
  The bundled Cortex Code skills create agents. When an agent misreads a question, fix it with an
  `AI_SQL_GENERATION` rule in the view, not with verified queries.
- **Business Ontology**: the bundled `$business-ontology` skill can import the terms of the view into the ontology.
  It writes governed, shared terms: only after the user's explicit yes.
- **Schedule**: the view reads the CDM tables live, so it needs no job. Run step 11 after each change of the model.
