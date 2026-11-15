# Business and semantic context on Snowflake

Snowflake often knows the user's business already: Cortex Sense contexts, Business Ontology terms, existing tables
and how people query them. Use that knowledge before writing code, so the new pipeline or model fits what exists.

1. **Before any code, collect the context.** Run (`collect-snowflake-context`) when another toolkit builds context:
   - in **`find-source`** (rest-api-pipeline): once the user has said what they want from the data, before any
     pipeline code;
   - in **`annotate-sources`** (transformations): once the source schemas are extracted, before the business
     entities.

   It writes `.dlthub/ontology/<slug>/context.md`. When that file exists for the topic and the user's intent has not
   changed, read it instead of collecting again. Then go on with the calling skill.
2. **Use the business names.** When a Business Ontology node matches a concept, use its name, definition and
   synonyms in `taxonomy.json` and in the model. The scope constraint of `annotate-sources` still applies: a concept
   needs columns in the source.
3. **Existing data first.** When the context finds that the data already exists in the account (verdict WARN or
   CONFLICT), tell the user before any pipeline code is written, and let them decide.
4. **Semantic view after the model.** Once the CDM tables are loaded into Snowflake, offer
   (`create-snowflake-semantic-view`), so Cortex Analyst and agents can answer the questions from `context.md`.
5. **Read only, unless the user says yes.** Never write to Business Ontology, Cortex Sense contexts or the comments
   of tables that other teams own without the user's explicit yes.
