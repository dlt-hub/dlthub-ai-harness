from typing import Dict, List, Literal, Optional, Type

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ontology metadata models
# ---------------------------------------------------------------------------


class TableMapping(BaseModel):
    table: str
    source_pipeline: str
    role: Literal["primary", "secondary"]


class ExcludedTable(BaseModel):
    table: str
    reason: str


class MergePolicy(BaseModel):
    conflict_strategy: Literal["prefer_source", "always_source", "field_level"] = "prefer_source"
    primary_source: Optional[str] = None
    field_level_priority: Dict[str, str] = Field(default_factory=dict)
    include_policy: Literal["union", "intersection"] = "union"


class ConceptMeta(BaseModel):
    description: str
    use_cases: List[str]
    references: List[str] = Field(default_factory=list)
    tables: List[TableMapping] = Field(default_factory=list)
    natural_key: Optional[str] = Field(
        default=None,
        description=(
            "Business / stitching key: source column name(s) as in the pipeline (e.g. id, properties__email). "
            "Use '+' for composite keys (CDM or source names), e.g. 'id+activity_type' for UNIONed activity types."
        ),
    )
    assumptions: List[str] = Field(default_factory=list)
    merge_policy: Optional[MergePolicy] = None


class Relationship(BaseModel):
    label: str
    from_entity: str
    to_entity: str
    via: str = Field(
        description="Join path: association table name, pattern, or free-text note for implementers.",
    )
    cardinality: Literal["one-to-one", "one-to-many", "many-to-many"]
    master_source: Optional[str] = None
    note: Optional[str] = None


class Ontology(BaseModel):
    version: str
    cdm_name: str
    concepts: Dict[str, ConceptMeta]
    relationships: List[Relationship] = Field(default_factory=list)
    excluded_tables: List[ExcludedTable] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    semantic_gaps: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Typed entity classes — canonical CDM attributes per entity
# ---------------------------------------------------------------------------


class OntologyEntity(BaseModel):
    """Marker base for CDM entity shapes; no shared fields — downstream tools match keys to ConceptMeta."""


class Company(OntologyEntity):
    """An organisation tracked in the CRM."""

    # natural key
    company_id: str  # id
    # identity
    name: Optional[str] = None  # properties__name
    domain: Optional[str] = None  # properties__domain
    # profile
    industry: Optional[str] = None  # properties__industry
    company_type: Optional[str] = None  # properties__type
    description: Optional[str] = None  # properties__description
    employee_count: Optional[str] = None  # properties__numberofemployees
    annual_revenue: Optional[str] = None  # properties__annualrevenue
    # location
    country: Optional[str] = None  # properties__country
    city: Optional[str] = None  # properties__city
    state: Optional[str] = None  # properties__state
    zip_code: Optional[str] = None  # properties__zip
    address: Optional[str] = None  # properties__address
    # contact
    phone: Optional[str] = None  # properties__phone
    website: Optional[str] = None  # properties__website
    linkedin_url: Optional[str] = None  # properties__linkedin_company_page
    timezone: Optional[str] = None  # properties__timezone
    # crm meta
    lifecycle_stage: Optional[str] = None  # properties__lifecyclestage
    owner_id: Optional[str] = None  # properties__hubspot_owner_id
    # custom fields
    product: Optional[str] = None  # properties__product
    stack_used: Optional[str] = None  # properties__stack_used
    # timestamps
    created_at: Optional[str] = None  # properties__createdate
    modified_at: Optional[str] = None  # properties__hs_lastmodifieddate
    is_archived: Optional[bool] = None  # archived


class Person(OntologyEntity):
    """An individual contact at a company."""

    # keys: contact_id = HubSpot surrogate; natural_key in ConceptMeta is properties__email for stitching
    contact_id: str  # id
    email: Optional[str] = Field(default=None, description="properties__email — business natural key for cross-source stitch")
    # identity
    first_name: Optional[str] = None  # properties__firstname
    last_name: Optional[str] = None  # properties__lastname
    job_title: Optional[str] = None  # properties__jobtitle
    company_name: Optional[str] = None  # properties__company (text, not FK)
    # contact
    phone: Optional[str] = None  # properties__phone
    mobile_phone: Optional[str] = None  # properties__mobilephone
    website: Optional[str] = None  # properties__website
    linkedin_url: Optional[str] = None  # properties__linkedin
    github_url: Optional[str] = None  # properties__github
    slack_username: Optional[str] = None  # properties__slack_user_name
    # location
    address: Optional[str] = None  # properties__address
    city: Optional[str] = None  # properties__city
    country: Optional[str] = None  # properties__country
    zip_code: Optional[str] = None  # properties__zip
    # crm meta
    lifecycle_stage: Optional[str] = None  # properties__lifecyclestage
    lead_status: Optional[str] = None  # properties__hs_lead_status
    engagement_stage: Optional[str] = None  # properties__engagement_stage (custom)
    priority: Optional[str] = None  # properties__priority (custom)
    owner_id: Optional[str] = None  # properties__hubspot_owner_id
    # timestamps
    created_at: Optional[str] = None  # properties__createdate
    modified_at: Optional[str] = None  # properties__lastmodifieddate
    is_archived: Optional[bool] = None  # archived


class Activity(OntologyEntity):
    """
    A discrete interaction event — unified UNION of meetings, notes, tasks, tickets.
    activity_type discriminator: 'meeting' | 'note' | 'task' | 'ticket'
    occurred_at = properties__hs_createdate (meetings/notes/tasks) or properties__createdate (tickets)
    Type-specific fields are null when the activity_type does not carry them.
    """

    # keys
    activity_id: str  # id
    activity_type: str  # discriminator added in transformation
    # common timestamps
    occurred_at: Optional[str] = None  # hs_createdate / createdate (see above)
    modified_at: Optional[str] = None  # properties__hs_lastmodifieddate
    is_archived: Optional[bool] = None  # archived
    # notes-only
    body: Optional[str] = None  # properties__hs_note_body (notes)
    owner_id: Optional[str] = None  # properties__hubspot_owner_id (notes)
    # tickets-only
    subject: Optional[str] = None  # properties__subject (tickets)
    pipeline: Optional[str] = None  # properties__hs_pipeline (tickets)
    pipeline_stage: Optional[str] = None  # properties__hs_pipeline_stage (tickets)


class Deal(OntologyEntity):
    """A commercial opportunity in the sales pipeline."""

    # natural key
    deal_id: str  # id
    # identity
    deal_name: Optional[str] = None  # properties__dealname
    deal_stage: Optional[str] = None  # properties__dealstage
    pipeline: Optional[str] = None  # properties__pipeline
    amount: Optional[str] = None  # properties__amount
    # timestamps
    created_at: Optional[str] = None  # properties__createdate
    close_date: Optional[str] = None  # properties__closedate
    modified_at: Optional[str] = None  # properties__hs_lastmodifieddate
    is_archived: Optional[bool] = None  # archived


ENTITY_MODELS: Dict[str, Type[OntologyEntity]] = {
    "Company": Company,
    "Person": Person,
    "Activity": Activity,
    "Deal": Deal,
}


# ---------------------------------------------------------------------------
# Shared constants for this CDM (single HubSpot source)
# ---------------------------------------------------------------------------

SOURCE_PIPELINE_HUBSPOT = "hubspot_crm_data"

def _single_source_merge() -> MergePolicy:
    """New instance per concept so in-place edits never leak across concepts."""
    return MergePolicy(
        conflict_strategy="always_source",
        primary_source=SOURCE_PIPELINE_HUBSPOT,
        include_policy="union",
    )

_R_JUNCTION = "HubSpot junction table — used in transformation joins only"

_HUBSPOT_JUNCTION_TABLES: List[str] = [
    "companies__associations__contacts__results",
    "companies__associations__deals__results",
    "companies__associations__meetings__results",
    "companies__associations__notes__results",
    "companies__associations__tasks__results",
    "companies__associations__tickets__results",
    "contacts__associations__companies__results",
    "contacts__associations__deals__results",
    "contacts__associations__meetings__results",
    "contacts__associations__notes__results",
    "contacts__associations__tasks__results",
    "contacts__associations__tickets__results",
    "deals__associations__companies__results",
    "deals__associations__contacts__results",
    "deals__associations__meetings__results",
    "deals__associations__notes__results",
    "deals__associations__tasks__results",
    "meetings__associations__companies__results",
    "meetings__associations__contacts__results",
    "meetings__associations__deals__results",
    "notes__associations__companies__results",
    "notes__associations__contacts__results",
    "notes__associations__deals__results",
    "tasks__associations__companies__results",
    "tasks__associations__contacts__results",
    "tasks__associations__deals__results",
    "tickets__associations__companies__results",
    "tickets__associations__contacts__results",
    "tickets__associations__deals__results",
]

_EXCLUDED_TABLES: List[ExcludedTable] = [
    ExcludedTable(table="leads", reason="out of scope per user decision"),
    ExcludedTable(table="leads__associations__companies__results", reason="junction table for excluded leads entity"),
    ExcludedTable(table="leads__associations__contacts__results", reason="junction table for excluded leads entity"),
    ExcludedTable(table="line_items", reason="commercial sub-record on deals, not an interaction activity"),
    ExcludedTable(table="line_items__associations__deals__results", reason="junction table for excluded line_items"),
    ExcludedTable(table="quotes", reason="commercial document attached to deals, not an interaction activity"),
    ExcludedTable(table="quotes__associations__deals__results", reason="junction table for excluded quotes"),
    ExcludedTable(table="deals__associations__line_items__results", reason="junction table for excluded line_items"),
    ExcludedTable(table="deals__associations__quotes__results", reason="junction table for excluded quotes"),
    *[ExcludedTable(table=t, reason=_R_JUNCTION) for t in _HUBSPOT_JUNCTION_TABLES],
]


# ---------------------------------------------------------------------------
# Ontology instance
# ---------------------------------------------------------------------------

ontology = Ontology(
    version="1.2",
    cdm_name="company_activity_stream",
    concepts={
        "Company": ConceptMeta(
            description="An organisation tracked in the CRM — the primary account entity interactions are linked to",
            use_cases=["track interactions with companies", "understand company engagement history"],
            references=["account", "organisation"],
            tables=[
                TableMapping(table="companies", source_pipeline=SOURCE_PIPELINE_HUBSPOT, role="primary"),
            ],
            natural_key="id",
            merge_policy=_single_source_merge(),
            assumptions=["Single source — no cross-source conflict; always_source trivially applied"],
        ),
        "Person": ConceptMeta(
            description="An individual contact at a company — the person involved in interactions",
            use_cases=["track interactions with people", "link contacts to companies"],
            references=["contact", "individual"],
            tables=[
                TableMapping(table="contacts", source_pipeline=SOURCE_PIPELINE_HUBSPOT, role="primary"),
            ],
            natural_key="properties__email",
            merge_policy=_single_source_merge(),
            assumptions=[
                "Single source — email is the business natural key for future cross-source joins; contact_id is the HubSpot surrogate",
            ],
        ),
        "Activity": ConceptMeta(
            description="A discrete interaction event — unified UNION of meetings, notes, tasks, tickets with activity_type discriminator",
            use_cases=["track all interactions with companies and people", "build an activity timeline per company/contact"],
            references=["meeting", "note", "task", "ticket", "interaction", "engagement"],
            tables=[
                TableMapping(table="meetings", source_pipeline=SOURCE_PIPELINE_HUBSPOT, role="primary"),
                TableMapping(table="notes", source_pipeline=SOURCE_PIPELINE_HUBSPOT, role="primary"),
                TableMapping(table="tasks", source_pipeline=SOURCE_PIPELINE_HUBSPOT, role="primary"),
                TableMapping(table="tickets", source_pipeline=SOURCE_PIPELINE_HUBSPOT, role="primary"),
            ],
            natural_key="id+activity_type",
            merge_policy=_single_source_merge(),
            assumptions=[
                "UNION of four tables; activity_type discriminator column added in transformation",
                "occurred_at = properties__hs_createdate for meetings/notes/tasks; properties__createdate for tickets",
                "properties__hs_timestamp (note interaction time) dropped in favour of consistent occurred_at across all types",
                "Type-specific fields (body, subject, pipeline*) are NULL for activity types that don't carry them",
            ],
        ),
        "Deal": ConceptMeta(
            description="A commercial opportunity in the sales pipeline, linked to a company and one or more contacts",
            use_cases=["track commercial pipeline", "link activities to revenue opportunities"],
            references=["opportunity", "pipeline"],
            tables=[
                TableMapping(table="deals", source_pipeline=SOURCE_PIPELINE_HUBSPOT, role="primary"),
            ],
            natural_key="id",
            merge_policy=_single_source_merge(),
            assumptions=["Single source — no cross-source conflict"],
        ),
    },
    relationships=[
        Relationship(
            label="BELONGS_TO",
            from_entity="Person",
            to_entity="Company",
            via="contacts__associations__companies__results",
            cardinality="many-to-many",
            note="A contact can be associated with multiple companies in HubSpot",
        ),
        Relationship(
            label="INVOLVES_COMPANY",
            from_entity="Activity",
            to_entity="Company",
            via="<type>__associations__companies__results (one table per activity type)",
            cardinality="many-to-many",
            note="Resolved by joining each activity type's own association table",
        ),
        Relationship(
            label="INVOLVES_PERSON",
            from_entity="Activity",
            to_entity="Person",
            via="<type>__associations__contacts__results (one table per activity type)",
            cardinality="many-to-many",
            note="Resolved by joining each activity type's own association table",
        ),
        Relationship(
            label="LINKED_TO_DEAL",
            from_entity="Activity",
            to_entity="Deal",
            via="<type>__associations__deals__results (one table per activity type)",
            cardinality="many-to-many",
            note="Optional — not all activities have a deal; tickets have no deal association table in this dataset",
        ),
        Relationship(
            label="LINKED_TO_COMPANY",
            from_entity="Deal",
            to_entity="Company",
            via="deals__associations__companies__results",
            cardinality="many-to-many",
        ),
        Relationship(
            label="DEAL_INVOLVES_PERSON",
            from_entity="Deal",
            to_entity="Person",
            via="deals__associations__contacts__results",
            cardinality="many-to-many",
        ),
    ],
    excluded_tables=_EXCLUDED_TABLES,
    assumptions=[
        f"Single source ({SOURCE_PIPELINE_HUBSPOT} on BigQuery) — no cross-source merging required; all merge policies are trivially always_source",
        "Activity is a unified UNION of meetings + notes + tasks + tickets with activity_type discriminator column",
        "Activity CDM identity is composite: activity_id + activity_type (per natural_key id+activity_type)",
        "occurred_at uses properties__hs_createdate for meetings/notes/tasks and properties__createdate for tickets (logged time, not actual interaction time)",
        "properties__hs_timestamp on notes (actual interaction time) dropped in favour of consistent occurred_at across all activity types",
        "Association tables are used only as join bridges in the transformation — they are not CDM entities",
        "owner_id is a HubSpot numeric user ID — no users table present to resolve to name/email",
    ],
    semantic_gaps=[
        "meetings table is very sparse: no title, description, duration, outcome, or attendee count — check if HubSpot pipeline fetches full meeting properties (hs_meeting_title, hs_meeting_body, hs_meeting_outcome, hs_meeting_duration)",
        "tasks table has no body/description field — cannot determine what each task is about",
        "No email or call activity types — HubSpot email send/open/click and call engagement objects would significantly enrich the activity stream but are not present in this dataset",
        "owner_id is unresolvable to a name/email — no HubSpot users table in the dataset; enriching with a users lookup would improve activity attribution",
        "notes properties__hs_timestamp (actual interaction time) is dropped — if precise interaction timing is needed for notes, consider preserving it as a separate activity_at field",
    ],
)
