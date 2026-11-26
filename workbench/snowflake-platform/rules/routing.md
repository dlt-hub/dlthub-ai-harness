# Snowflake routing

Deploying, running or scheduling jobs on Snowflake, their environments and the runner install go to the skills of
this toolkit, which are installed already. Their descriptions say which skill fits. They win over `dlthub-router` for
these intents; install nothing. The workflow entry is `prepare-deployment`.

- A new pipeline or model still starts in its own toolkit (`find-source`, `annotate-sources`).
- Snowflake as a destination, the context of the account, semantic views and dynamic tables go to the
  destination-snowflake toolkit.
