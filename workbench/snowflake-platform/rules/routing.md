# Snowflake routing

Snowflake intents go to the skills of this toolkit, which are installed already: deploying, running or scheduling
jobs on Snowflake, Snowflake as a destination, what the account already knows, semantic views, the runner install.
Their descriptions say which skill fits. They win over `dlthub-router` for Snowflake intents; install nothing. The
workflow entry is `setup-snowflake-workspace`.

- A new pipeline or model still starts in its own toolkit (`find-source`, `annotate-sources`). The
  `Business and semantic context on Snowflake` rule says where `collect-snowflake-context` joins them.
- Snowflake objects that dlthub did not create (other tasks, streams, dynamic tables) are not ours: use the
  bundled Cortex Code skills for them.
