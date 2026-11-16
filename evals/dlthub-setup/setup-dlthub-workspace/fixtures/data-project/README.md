# acme-analytics

Ad-hoc analytics for the ops team. `scripts/ingest_orders.py` pulls orders from
the Shopify API into `data/orders.csv`; `scripts/push_to_snowflake.py` uploads it.
