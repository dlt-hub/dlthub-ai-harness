---
name: generate-cdm
description: Generate a Canonical Data Model (CDM) from a finalized ontology. Use when the user has completed their ontology and wants to create a standardized data model with entities, relationships, and validation rules. The CDM bridges the semantic ontology to implementation-ready data structures.
argument-hint: "[-- [entity-focus or hints]]"
---

# Generate Canonical Data Model from Ontology

**Transforms your ontology into an implementation-ready Canonical Data Model (CDM).** The ontology captures business semantics; the CDM translates those semantics into standardized entities, relationships, and validation rules that can be implemented in any data system.

Parse `$ARGUMENTS`:
- `entity-focus` (optional, after `--`): specific entity to focus on (e.g., `-- Customer`) or hints about CDM priorities.

## Steps

### 1. Extract core business entities

Read `.schema/ontology.ison`. If the file doesn't exist or is empty, stop and ask the user to run `create-ontology` first.

From the ontology, list every noun defined as a real-world object. These become **CDM entities**.

For each entity, extract:
- Canonical name (from ontology, not source systems)
- Description / semantic meaning
- Attributes with data types
- Whether attributes are inferred or explicit in the ontology

| Entity type | Standard attributes to include |
|---|---|
| Order/Transaction | id, timestamp, status, total, currency |
| User/Customer | id, email, created_at, status |
| Product | id, name, price, sku, description |
| Subscription | id, start_date, end_date, plan, status |
| Address | id, street, city, country, postal_code |

**Kimball alignment**: Entities map to fact and dimension table subjects. Ensure atomic detail (Kimball Rule #1).

#### Entity equivalence check

**Before finalizing any entity**, check whether it is genuinely new or just an alias for an entity already in the ontology.

Different source systems and teams often use different names for the same real-world concept:

| Concept | Common aliases |
|---|---|
| Person who interacts with the business | Contact, User, Profile, Member, Person, Lead, Account |
| Legal/commercial counterpart | Company, Organization, Account, Firm, Client, Vendor, Partner |
| Commercial opportunity | Deal, Opportunity, Sale, Pipeline, Prospect |
| Purchase event | Order, Transaction, Invoice, Purchase, Booking |
| Recurring charge | Subscription, Plan, Contract, License |

For each candidate entity, ask:
- **Is there an existing entity that describes the same real-world object?** If yes, use the existing entity — add an alias or note in the description if the naming differs across systems.
- **Is this genuinely a different concept, or the same concept in a different lifecycle stage?** (e.g., Lead vs Customer — both are people, but at different stages. Either merge them with a `status` field, or keep them separate with explicit justification.)
- **Does the difference justify a separate entity, or is it just a source system artefact?** Source systems name things after their own domain (HubSpot calls it "Contact", Salesforce calls it "Lead") — the CDM should use the canonical business concept, not the source system label.

If two entities are equivalent: collapse them into one with the most semantically precise name, and document the aliases. If they are genuinely distinct: keep them separate and document *why* they are distinct.

### 2. Map elementary facts (relationships)

Extract every relationship the ontology defines as a fundamental, irreducible fact:
- `Customer` **places** `Order`
- `Order` **contains** `OrderLine`
- `OrderLine` **references** `Product`

For each relationship, capture:
- Source entity → relationship type → target entity
- Cardinality (one-to-one, one-to-many, many-to-many)
- Whether mandatory or optional
- Semantic label (e.g., `PLACES`, `CONTAINS`, `MEMBER_OF`)

Do **not** flatten or collapse facts — preserve semantic richness. Relationships are first-class citizens, not just foreign keys.

### 3. Apply dimensional modeling design

Source: [Kimball dimensional modeling techniques](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/)

For each entity identified in Steps 1–2, make three design decisions:

#### A. Classify as fact or dimension

| Classify as **fact** if… | Classify as **dimension** if… |
|---|---|
| It records a business event or measurement (order placed, payment made, page viewed) | It describes the *who, what, where, when, why* context of events |
| It has numeric/additive measures (amount, quantity, duration) | It has descriptive attributes (name, category, status, address) |
| Rows are created when something *happens* | Rows represent things that *exist* |

Fact table types to choose from:
- **Transaction** — one row per event (most common)
- **Periodic snapshot** — one row per entity per time period (e.g., daily account balance)
- **Accumulating snapshot** — one row per process instance with multiple milestone dates (e.g., order lifecycle)
- **Factless** — events with no measures (e.g., student attendance, product views)

#### B. Define grain for every fact table

The grain is the single sentence that describes what one row in the fact table represents. Define it before adding any columns.

> "One row per order line item per order" ✓
> "One row per order" ✓
> "Order data" ✗ — too vague

Once the grain is set, every measure and foreign key must be consistent with it. Reject any attribute that implies a different grain.

#### C. Surrogate keys and slowly changing dimensions (for dimensions)

Every dimension table needs a **surrogate key** — a system-generated integer or UUID, independent of natural/business keys. This is the primary key used in fact table foreign keys.

| SCD Type | Behaviour | When to use |
|---|---|---|
| Type 0 | Never change (retain original) | Fixed reference data (country codes) |
| Type 1 | Overwrite — no history kept | Corrections, non-analytical attributes |
| Type 2 | Add new row — full history kept | Analytically important changes (customer segment, product price) |
| Type 3 | Add previous-value column | Limited history for a specific attribute |

Default to **Type 1** unless historical tracking of that attribute is analytically required, then use **Type 2** (adds `valid_from`, `valid_to`, `is_current` columns).

#### D. Conformed dimensions

A dimension is **conformed** if it is shared across multiple fact tables (e.g., a `Date` dimension used by both `Order` and `Payment` facts). Identify conformed dimensions early — they are the integration points of the enterprise model and must be agreed upon before transformation is built.

Present the full classification to the user for review before proceeding.

### 4. Extract validation rules and constraints

Capture business rules from the ontology that constrain entity behavior:
- "A Customer can only have one BillingAddress marked as primary"
- "An Order must reference an active Customer"
- "InvoiceDate must always be ≥ OrderDate"

These become validation logic in the CDM.

### 5. Handle nulls and unknowns intentionally

For every optional attribute or relationship:
- Define explicit sentinel values (`UNKNOWN`, `NOT_APPLICABLE`)
- Document *why* a value might be absent based on ontology semantics

Example: `ShippingAddress` is null for digital products — not a data quality issue, but because digital products have no physical fulfillment.

**Kimball alignment**: Never use null as a foreign key (Rule #6).

### 6. Preserve temporal semantics

For time-sensitive facts (e.g., "subscription is active during a period"):
- Use `valid_from` / `valid_to` columns for slowly changing entities
- Store dates as proper date/datetime types, never strings
- Document the canonical timezone standard

**Kimball alignment**: Store dates using date types or surrogate keys to date dimension (Rule #9).

### 7. Identify semantic gaps

Compare ontology entities against available source data (if `.schema/<dataset>.ison` exists):
- Fields in source that don't map to ontology concepts
- Ontology entities with no source system representation

**Before proposing a new entity to fill a gap**, apply the entity equivalence check from Step 1. A source table named `users` is not automatically a new CDM entity — it may map to an existing `Customer` or `Contact` entity. Only propose a new entity if no existing entity covers the same real-world concept.

Present gaps to the user for resolution before finalizing CDM.

### 8. Generate CDM in ISON format

Save the CDM to `.schema/CDM.ison` using ISON format ([spec](https://ison.dev/spec.html)):

```
meta.cdm
version created_from
1.0 ontology.jsonld

table.entities
id:string name:string description:string table_type:string grain:string surrogate_key:string scd_type:string conformed:bool
Customer Customer "A person or organization that purchases products" dimension "" customer_sk 1 true
Order Order "A commercial transaction initiated by a customer" fact "One row per order line item per order" "" 0 false
Product Product "An item available for purchase" dimension "" product_sk 2 true

table.attributes
entity:ref name:string type:string nullable:bool description:string
:Customer customer_sk int false "Surrogate key (system-generated, use as FK in facts)"
:Customer customer_id string false "Natural/business key"
:Customer email string false "Primary contact email"
:Customer created_at datetime false "Account creation timestamp"
:Customer status string false "Account status (active, inactive, suspended)"
:Order order_id string false "Degenerate dimension — transaction identifier stored in fact"
:Order customer_sk int false "FK to Customer dimension"
:Order product_sk int false "FK to Product dimension"
:Order order_date datetime false "When order was placed"
:Order total float false "Order total amount"
:Order currency string false "ISO 4217 currency code"

table.relationships
from:ref to:ref type:string cardinality:string mandatory:bool description:string
:Order :Customer :PLACED_BY many_to_one true "Fact references customer dimension"
:Order :Product :CONTAINS many_to_one true "Fact references product dimension"

table.validation_rules
id:string entities:string rule_type:string expression:string description:string
VR001 "Invoice,Order" cross_entity "invoice_date >= order_date" "Invoice cannot precede order"
VR002 Customer single_entity "status IN ('active','inactive','suspended')" "Valid customer statuses"

table.null_semantics
entity:ref attribute:string sentinel:string reason:string
:Order shipping_address NOT_APPLICABLE "Digital products have no shipping"
:Customer phone UNKNOWN "Not collected at signup"
```

Key fields in `table.entities`:
- `table_type`: `fact` or `dimension`
- `grain`: sentence describing one row (facts only; empty for dimensions)
- `surrogate_key`: name of the system-generated PK column (dimensions only)
- `scd_type`: `0`, `1`, `2`, or `3` (dimensions only; use `0` for facts)
- `conformed`: `true` if this dimension is shared across multiple fact tables

## Output

```
CDM generated: .schema/CDM.ison

Entities: <count>
- <Entity1>: <description>
- <Entity2>: <description>
...

Relationships: <count>
- <Entity1> -[<TYPE>]-> <Entity2> (<cardinality>)
...

Validation rules: <count>
Semantic gaps identified: <count or "none">

Next steps:
- Review .schema/CDM.ison for accuracy
- Resolve any semantic gaps with domain experts
- Use `create-transformation` to map source data to this CDM
```