# Cortex Code

Cortex Code reads the skill list and `CORTEX.md` once, when the session starts. After a toolkit install, or when
new skills appear in `.cortex/skills/`:

- A skill that is not in your skill list is usable now: read `.cortex/skills/<name>/SKILL.md` and follow it,
  before you say that a skill does not exist. Do not reinstall a toolkit because its skills are missing from the
  list.
- Read the dltHub rules section of `CORTEX.md` again and follow the new rules from now on.
- Tell the user in one line what is new, and that a new session lists it.

For Snowflake work that the dltHub skills do not cover (objects dlthub did not create, the refresh history and lag
of dynamic tables, Business Ontology, questions to a semantic view), use the bundled Cortex Code skills
(`$cortex-sense`, `$business-ontology`, `$query-semantic-view`) and the SQL tool.
