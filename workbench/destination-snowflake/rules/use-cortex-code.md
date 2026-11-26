# Snowflake internals: hand over to Cortex Code

Cortex Code is Snowflake's coding agent and knows the Snowflake internals: the objects of the account and their
history and lineage, Business Ontology and Cortex Sense, semantic views and Cortex Analyst, the refresh and lag of
dynamic tables, warehouse sizing. When a task needs these, offer to hand it over: Cortex Code runs it as a subagent
with the context of this session, and you go on with its answer (`delegate-to-cortex-code`). Hand nothing over
without the user's yes.
