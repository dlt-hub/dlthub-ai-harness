# Snowflake rules that shape a semantic view

Read this at steps 2–9 of `create-snowflake-semantic-view`. The rules marked "verified" were tested on Snowflake in
November 2026, on a CDM of 12 logical tables. The docs do not say all of them yet.

## Rules

- **No self-references.** A logical table cannot reference itself (employee → manager). Declare a second logical
  table over the same physical table (`sales_reps` and `managers` over `DIM_EMPLOYEE`) and relate them. Verified: two
  logical tables over one physical table deploy and query.
- **Relationships are many-to-one or one-to-one.** The referenced columns must be the `PRIMARY KEY` or a `UNIQUE` key
  of the referenced logical table.
- **One path between two tables.** Several relationships between the same two tables are restricted. For role-playing
  dates (ordered, shipped, paid), define date dimensions on the fact from its own date columns
  (`DATE_TRUNC('quarter', orders.shipped_at)`), instead of joining the date dimension several times. A dimension
  reachable by two paths gets a copy with a role name (`order_stages` and `change_stages`).
- **Granularity.** A fact or dimension can use columns of the tables it points to (many-to-one). A value from the
  "many" side needs an aggregate.
- **Roll-ups use defined names.** A cross-table roll-up (`orders.line_count AS COUNT(order_lines.line_id)`) must
  reference facts or dimensions that the view defines, not raw columns. Verified: the first deploy of a full view
  failed on this.
- **New names for changed values.** When an expression changes a column, give the fact or dimension its own name.
  A boolean stage column gets its own dimension (`stages.is_won AS stages.stage_is_won`). Facts on a related table
  can then use it (`deals.won_amount AS CASE WHEN stages.stage_is_won THEN deals.amount ELSE 0 END`). Verified.
- **Dates relative to today** (`DATEDIFF('day', orders.ordered_at, CURRENT_DATE())`) work as dimensions and in
  `WHERE`. Verified.
- **Metrics aggregate.** Ratios across tables are derived metrics, without a table prefix, built from other metrics.
  Snapshot measures use `NON ADDITIVE BY`.
- **Privileges.** `CREATE SEMANTIC VIEW` on the schema and `SELECT` on the tables. Querying needs `SELECT` on the
  view.

## Clause order

`TABLES`, `RELATIONSHIPS`, `FACTS`, `DIMENSIONS`, `METRICS`, then `COMMENT`, `AI_SQL_GENERATION`,
`AI_VERIFIED_QUERIES`. A clause out of order fails to compile.

## A small complete view

It shows the shape and the clause order. This exact view was not deployed.

```sql
-- sales_model: orders, customers, sales reps and their managers
CREATE OR REPLACE SEMANTIC VIEW ANALYTICS.SALES_MODEL.SALES_MODEL_SV
  TABLES (
    orders AS ANALYTICS.SALES_MODEL.FACT_ORDER PRIMARY KEY (order_sk)
      WITH SYNONYMS ('sales', 'purchases') COMMENT = 'One order placed by a customer.',
    customers AS ANALYTICS.SALES_MODEL.DIM_CUSTOMER PRIMARY KEY (customer_sk)
      WITH SYNONYMS ('account', 'client') COMMENT = 'A company that buys from us.',
    sales_reps AS ANALYTICS.SALES_MODEL.DIM_EMPLOYEE PRIMARY KEY (employee_sk)
      COMMENT = 'The employee who owns the order.',
    -- a second logical table over DIM_EMPLOYEE: no self-reference
    managers AS ANALYTICS.SALES_MODEL.DIM_EMPLOYEE PRIMARY KEY (employee_sk)
      COMMENT = 'The manager of a sales rep.'
  )
  RELATIONSHIPS (
    orders_to_customers AS orders (customer_sk) REFERENCES customers,
    orders_to_sales_reps AS orders (sales_rep_employee_sk) REFERENCES sales_reps,
    sales_reps_to_managers AS sales_reps (manager_employee_sk) REFERENCES managers
  )
  FACTS (
    orders.net_amount AS orders.amount - orders.discount COMMENT = 'Order amount after discounts.'
  )
  DIMENSIONS (
    orders.order_month AS DATE_TRUNC('month', orders.ordered_at) COMMENT = 'Month the order was placed.',
    customers.segment AS customers.customer_segment WITH SYNONYMS ('tier'),
    sales_reps.rep_name AS sales_reps.full_name,
    managers.manager_name AS managers.full_name
  )
  METRICS (
    orders.revenue AS SUM(orders.net_amount) WITH SYNONYMS ('sales', 'turnover')
      COMMENT = 'Net revenue after discounts. The default meaning of revenue.',
    orders.order_count AS COUNT(orders.order_sk),
    average_order_value AS orders.revenue / NULLIF(orders.order_count, 0)
  )
  COMMENT = 'Sales orders by customer, rep and manager.'
  AI_SQL_GENERATION 'Amounts are in EUR. The fiscal year is the calendar year. Exclude customers with segment
''Unknown''.';
```
