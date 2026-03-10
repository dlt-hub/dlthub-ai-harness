# Transformations workflow

## Workflow Entry

**ALWAYS** start with **Create ontology** (`create-ontology`) — define your business entities and relationships before generating a CDM or writing transformations.

## Core workflow

1. **Define your data model** (`create-ontology`) — capture business entities and relationships as a structured ontology
2. **Generate canonical model** (`generate-cdm`) — translate the ontology into implementation-ready entities, relationships, and validation rules
3. **Ingest source data** — load raw data via `rest-api-pipeline` or other dlt sources
4. **Transform to canonical model** (`create-transformation`) — map source tables to CDM entities

```
Business scenarios → create-ontology → ontology.ison
                                            ↓
                                      generate-cdm → CDM.dbml
                                            ↓
Raw source data → dlt pipeline(s) → create-transformation → Canonical dataset
```

## Skills

| Skill | Purpose |
|-------|---------|
| `create-ontology` | Define canonical entities and relationships |
| `generate-cdm` | Translate ontology into implementation-ready CDM |
| `create-transformation` | Map source data to CDM entities |

## Handover To Other Toolkits

- **rest-api-pipeline** — hand off to this toolkit before `create-transformation` if source data has not yet been ingested; use it to load raw data from REST APIs via dlt
- **data-exploration** — hand off after `create-transformation` to explore and validate the canonical dataset with marimo notebooks