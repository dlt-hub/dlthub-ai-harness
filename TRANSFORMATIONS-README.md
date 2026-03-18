# Transformations Toolkit

Transform raw dlt pipeline data into a Canonical Data Model. Annotate sources, build an entity ontology, design a Kimball-style CDM, and write `@dlt.hub.transformation` ibis functions.

## Installation

```bash
dlt ai toolkit transformations install --branch transformation-high-intent
```

## Example prompt

Once installed, start a new Claude Code session in your dlt project directory and try:

```
I have two dlt pipelines; hubspot_crm and luma_events. I want to build a data model
so I can track event attendance and link contacts to companies.
```

Claude will walk you through the full workflow:

1. **Annotate sources** — identify your pipelines, extract schemas, map tables to canonical concepts (e.g. `Person`, `Company`, `Event`), and confirm cross-source stitch keys
2. **Create ontology** — build an entity graph with attributes unioned from all contributing sources
3. **Generate CDM** — apply Kimball dimensional modeling (fact/dimension classification, surrogate keys, SCD types)
4. **Create transformation** — write `@dlt.hub.transformation` ibis functions that map source tables to CDM entities

## Requirements

- dlt installed as per main [README](https://github.com/dlt-hub/dlthub-ai-workbench/blob/master/README.md) installed and at least one local pipeline run or dataset available to be transformed.