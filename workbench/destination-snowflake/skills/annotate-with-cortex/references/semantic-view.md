# Semantic view from a dlt schema

## Skeleton the agent should produce

```sql
CREATE OR REPLACE SEMANTIC VIEW CORTEX_ON_LOAD.SHOP.SHOP_SV
  TABLES (
    orders AS CORTEX_ON_LOAD.SHOP.ORDERS
      PRIMARY KEY (_dlt_id)
      WITH SYNONYMS ('purchases', 'sales')
      COMMENT = 'One row per order; customer embedded as cust__* columns',
    orders__items AS CORTEX_ON_LOAD.SHOP.ORDERS__ITEMS
      PRIMARY KEY (_dlt_parent_id, _dlt_list_idx)
      COMMENT = 'One row per product line of an order'
  )
  RELATIONSHIPS (
    items_to_orders AS orders__items (_dlt_parent_id) REFERENCES orders
  )
  FACTS (
    orders.net_amount_c AS amt_c - disc_c COMMENT = 'Net amount in cents, all statuses'
  )
  DIMENSIONS (
    orders.revenue_month AS DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', ord_ts))::DATE
      WITH SYNONYMS ('month', 'period') COMMENT = 'UTC calendar month of the order',
    orders.country AS cust__ctry WITH SYNONYMS ('market'),
    orders.order_status AS sts,
    orders__items.product_category AS cat
  )
  METRICS (
    orders.net_revenue AS SUM(IFF(sts = 'C' AND COALESCE(cust__is_tst, FALSE) = FALSE, amt_c - disc_c, 0)) / 100.0
      WITH SYNONYMS ('revenue', 'net sales') COMMENT = 'Net revenue in USD, completed non-test orders',
    orders.completed_orders AS COUNT(DISTINCT IFF(sts = 'C' AND COALESCE(cust__is_tst, FALSE) = FALSE, id, NULL))
  )
  COMMENT = 'Net revenue per month and country for finance'
  AI_SQL_GENERATION 'Revenue counts completed orders only (sts = C). QA test accounts (cust__is_tst) never count. Money columns ending in _c are US cents. Months are UTC calendar months.';
```

## Rules of thumb that keep the DDL compiling and the answers right

- One logical table per dlt table. Root tables: `PRIMARY KEY (_dlt_id)`. Child tables (dlt
  `parent` set): `PRIMARY KEY (_dlt_parent_id, _dlt_list_idx)` and a relationship
  `child (_dlt_parent_id) REFERENCES parent`. dlt guarantees these columns exist.
- A dimension or metric lives on the logical table whose grain it has. Line-level columns
  (`cat`, `sku`, `qty`) go on the child table; putting them on the parent fans out or fails.
- Filters go inside each metric (`IFF(...)` or `CASE`) rather than as a global filter, so any slice
  of the view, by any dimension, respects them.
- Money in cents: divide in the metric, not in a fact used elsewhere, or document the fact unit.
- Time zones: `TIMESTAMP_LTZ` columns render in the session time zone. If the business month is
  UTC, use `CONVERT_TIMEZONE('UTC', col)` before `DATE_TRUNC`, and say so in the comment.
- Synonyms on tables, dimensions and metrics are what make natural-language questions land on the
  right object; copy them from the business context or the ontology.
- `AI_SQL_GENERATION` carries the business rules to Cortex Analyst and CoCo. Keep it to the rules
  that change a number, in one short paragraph.
- Leave PII columns out of dimensions unless the user asks for them.

## Proving it

```sql
SELECT * FROM SEMANTIC_VIEW(
  CORTEX_ON_LOAD.SHOP.SHOP_SV
  METRICS orders.net_revenue, orders.completed_orders
  DIMENSIONS orders.revenue_month
) ORDER BY revenue_month DESC LIMIT 3;

SELECT ROUND(SUM(amt_c - disc_c) / 100, 2), COUNT(*)
FROM CORTEX_ON_LOAD.SHOP.ORDERS
WHERE sts = 'C' AND COALESCE(cust__is_tst, FALSE) = FALSE
  AND CONVERT_TIMEZONE('UTC', ord_ts) >= '2026-10-01'
  AND CONVERT_TIMEZONE('UTC', ord_ts) <  '2026-11-01';
```

The two must agree to the cent. In Snowsight, the view's page under the schema shows the logical
tables, dimensions and metrics with their expressions; CoCo picks the view up on its own when asked
a question scoped to the schema.

## Reset

`DROP SEMANTIC VIEW IF EXISTS <view>`, `COMMENT ON COLUMN ... IS ''` for each column, and drop
the review table. The template's objects are all replaced on the next run anyway.
