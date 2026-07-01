Read SOUL.md before anything else — it defines who you are and how you operate.

## Toolkit routing

Match the user's intent to a toolkit, install it if needed, then invoke the parent skill of the same name.

```
intent                                                             → toolkit               | install                                                           | parent skill
load from a REST API / HTTP endpoint / web service (Stripe, GitHub…) → rest-api-pipeline    | dlthub --non-interactive ai toolkit install rest-api-pipeline     | rest-api-pipeline
load tables from a SQL database (Postgres, MySQL, Snowflake, …)      → sql-database-pipeline | dlthub --non-interactive ai toolkit install sql-database-pipeline | sql-database-pipeline
load files (CSV, Parquet, JSONL) from disk / S3 / GCS / Azure / SFTP → filesystem-pipeline  | dlthub --non-interactive ai toolkit install filesystem-pipeline   | filesystem-pipeline
```

## Disambiguation

- User says "load my database" — confirm whether it's a live SQL database (`sql-database-pipeline`) or files exported from a database (`filesystem-pipeline`) before routing.
- User says "load from Stripe / GitHub / Salesforce / HubSpot" — these are REST APIs, use `rest-api-pipeline`.
- User's source turns out to be file-based mid-flow (S3, GCS, local CSV, SFTP) — switch to `filesystem-pipeline`.
