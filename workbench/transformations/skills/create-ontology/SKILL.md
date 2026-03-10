---
name: create-ontology
description: Build or edit a data model ontology. Use when the user wants to create a data model, edit their data model, or asks how to get started with data modeling. Takes company name, a one-line business description, and main DB tables as input — then auto-completes the ontology using web research.
argument-hint: "[company name] | [one-line business description] | [comma-separated table names]"
---

# Create ontology from company context

**The ontology is the foundation of your data model.** It captures your business domain as a structured graph of entities and relationships, seeded from your existing tables and enriched with what's known about your industry.

**Keep Q&A to a minimum.** Ask for missing inputs once (see below), then proceed autonomously. Do not ask follow-up questions — make reasonable inferences, record every assumption in `table.assumptions`, and let the user correct them after reviewing the output.

Parse `$ARGUMENTS` — expect three pipe-separated values:
- `company` — company name (used for web research)
- `description` — one-line business model (e.g. "ride-sharing company")
- `tables` — comma-separated list of main DB tables (e.g. "rides, captains, vendor")

## Input prompt

If any of the three inputs are missing, ask for all three at once:

> To build your ontology I need three things:
>
> 1. **Company name** — used to research your domain online
> 2. **One-line business description** — e.g. "ride-sharing company", "B2B SaaS for HR teams"
> 3. **Main DB tables** — comma-separated list of your core tables
>
> Example: `HubSpot | B2B CRM and marketing automation platform | contacts, companies, deals, engagements`

**STOP and wait for input before proceeding.**

## Editing an existing ontology

If `.schema/ontology.ison` exists, read it first. Then:
- Merge new entities and relationships into the existing tables
- Preserve existing structure unless explicitly asked to replace it
- Show the user what changed: "Added 2 entities, updated 1 relationship."

## Steps

### 1. Research the company

Use the WebSearch tool to look up the company name. Find:
- What the company does (products, services, business model)
- Key domain concepts used in their industry
- Any known data model patterns for this domain (e.g. "ride-hailing platforms typically model routes, trips, drivers, passengers")

Use findings to inform entity and attribute inference in the steps below.

### 2. Seed entities from source tables

Each table the user listed is a confirmed entity. Add it to the ontology with:
- `source_table` set to the actual table name
- `inferred: false`

### 3. Infer additional entities

Based on web research and the domain, identify standard entities that likely exist but weren't listed as tables. Common patterns:

| Domain | Entities typically inferred |
|---|---|
| Ride-hailing / transit | Route, Booking, Vehicle, User/Passenger |
| E-commerce | OrderLine, Product, Payment, Address |
| SaaS / subscriptions | Subscription, Plan, Invoice, Feature |
| Marketplace | Listing, Review, Payout, Category |
| Logistics | Shipment, Warehouse, Carrier, TrackingEvent |

Mark these as `inferred: true`. They may not have a source table yet.

### 4. Define attributes for each entity

For each entity (both confirmed and inferred):
- Include standard attributes for its type (id, status, created_at, etc.)
- Add domain-specific attributes from web research
- Flag inferred attributes as `inferred: true`

Standard attributes by entity type:

| Entity type | Standard attributes |
|---|---|
| Event / transaction | id, status, created_at, currency, amount |
| Person / user | id, name, email, phone, status, created_at |
| Organisation / account | id, name, contact_email, status, created_at |
| Vehicle / asset | id, make, model, capacity, status, license_plate |
| Route / path | id, name, origin, destination, status |

### 5. Map relationships

For each pair of entities, define how they connect:
- Cardinality: `one_to_one`, `one_to_many`, `many_to_many`
- Mandatory or optional
- Semantic label in UPPER_SNAKE_CASE (e.g. `OPERATED_BY`, `BELONGS_TO`, `INSTANCE_OF`)

Default cardinality assumptions (override with web research):
- Transactions/events → their context entities: `many_to_one`, mandatory
- Users → organisations: `many_to_one`, optional
- Assets → their operators/owners: `many_to_one`, optional

### 6. State assumptions

Collect every inference made — entity existence, attribute inclusion, cardinality choice — into the `nodes.assumption` block. Be specific:

> "Assumed Route is a separate entity from Ride because ride-hailing platforms typically reuse routes across many trip instances."
> "Assumed Booking.fare is nullable — fare may not be settled at booking time."

### 7. Generate ontology in Graph ISON format

Save to `.schema/ontology.ison` using Graph ISON format ([spec](https://graph.ison.dev/)):

```
// meta: version=1.0 company="Acme Corp" business_model="ride-sharing company"

nodes.entity
id       source_table  inferred  description
Route    ""            true      "Reusable path template between origin and destination"
Ride     rides         false     "A scheduled trip instance on a Route"
Captain  captains      false     "A driver who operates Rides"

nodes.attribute
id                entity:ref       type      nullable  inferred  description
Route.route_id    :entity:Route    string    false     false     "Unique route identifier"
Route.name        :entity:Route    string    true      true      "Human-readable route label"
Route.origin      :entity:Route    string    true      true      "Starting point"
Route.destination :entity:Route    string    true      true      "Ending point"
Route.status      :entity:Route    string    true      true      "active | inactive | draft"
Ride.ride_id      :entity:Ride     string    false     false     "Unique ride identifier"
Ride.route_id     :entity:Ride     string    true      true      "FK → Route"
Ride.status       :entity:Ride     string    true      true      "scheduled | in_progress | completed | cancelled"
Ride.scheduled_at :entity:Ride     datetime  true      true      "Planned departure time"

edges.INSTANCE_OF
source        target          cardinality  mandatory  description
:entity:Ride  :entity:Route   many_to_one  true       "Many rides occur on the same route at different times"

edges.OPERATED_BY
source        target           cardinality  mandatory  description
:entity:Ride  :entity:Captain  many_to_one  true       "Each ride is driven by one captain"

nodes.assumption
id    entity           assumption
A001  :entity:Route    "Route inferred as a separate entity — ride-hailing platforms reuse routes across many trip instances"
A002  :entity:Booking  "Booking inferred as likely entity — platforms of this type track individual passenger reservations"
```

Also write `.schema/ontology.md` (human-readable summary of the same data):
- Company name and business description
- Entity list with one-line descriptions
- Relationship summary
- List of all assumptions made
- Note on inferred vs confirmed entities

## Output

```
Ontology created: .schema/ontology.ison

Confirmed entities (from your tables): <count>
- <Entity>: <description>

Inferred entities (from web research): <count>
- <Entity>: <description> [ASSUMPTION: <reason>]

Relationships: <count>
- <Entity> -[LABEL]-> <Entity> (<cardinality>)

Assumptions: <count> — see .schema/ontology.md for full list
```

**For edited ontology:**
```
Ontology updated: .schema/ontology.ison

Changes:
- Added: <new entities/relationships>
- Updated: <modified items>
- Removed: <deleted items, if any>

Current totals: <X> entities, <Y> relationships
```

**Next steps:**
- Review `.schema/ontology.ison` and correct any wrong assumptions
- Use `generate-cdm` to translate the ontology into an implementation-ready canonical data model
- Use `create-transformation` to map source data to the CDM
