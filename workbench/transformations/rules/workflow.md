# Transformations workflow

## Core workflow

1. **Define your data model** — Use `create-ontology` to capture business entities and relationships as a JSON-LD ontology
2. **Generate canonical model** — Use `generate-cdm` to translate the ontology into implementation-ready entities, relationships, and validation rules
3. **Ingest source data** — Load raw data via `rest-api-pipeline` or other dlt sources
4. **Transform to canonical model** — Use `create-transformation` to map source tables to CDM entities

```
Business scenarios → create-ontology → ontology.ison
                                            ↓
                                      generate-cdm → CDM.ison
                                            ↓
Raw source data → dlt pipeline(s) → create-transformation → Canonical dataset
```

## Skills

| Skill | Purpose |
|-------|---------|
| `create-ontology` | Define canonical entities and relationships |
| `generate-cdm` | Translate ontology into implementation-ready CDM |
| `create-transformation` | Map source data to CDM entities |

## Related toolkits

- **rest-api-pipeline** — ingest data from REST APIs before transforming
- **data-exploration** — explore transformed data with marimo notebooks

