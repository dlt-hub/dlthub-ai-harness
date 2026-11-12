"""Annotate a dlt dataset on Snowflake with a Cortex agent and build a view.

Copy this module into the dlt project and call `annotate(pipeline, business_context)`
from a dltHub job that follows the load job's success. One agent:run call with the CoCo code
toolset profiles the tables and answers with JSON; this module applies the answer
with plain SQL (comments, the semantic view) and loads the agent's report with dlt.
Adapt TASK to the business; keep the validation, it is what makes the job safe.
"""

import base64
import hashlib
import json
import time

import dlt
import requests
from dlt.common import pendulum

VIEW_SUFFIX = "_sv"
REVIEW_TABLE = "cortex_review"
AGENT_TIMEOUT = 900
DDL_RETRIES = 2

SYSTEM = (
    "You are the data side of a hand-off between a dlt pipeline and a Snowflake account. "
    "You have read-only SQL. Work only inside the schema named in the task. "
    "Answer with exactly one JSON object and nothing else: no markdown fences, no prose."
)

# Adapt the business context; keep the four steps and the answer format.
TASK = """\
A dlt pipeline loaded {dataset} into Snowflake. Tables and columns, as dlt knows them:
{schema}

Business context from the people who own the data (what the rows cannot tell you):
{context}

Take it from here, you have the data:
1. Profile every table listed above and check each statement of the business context against
   the data. Note what holds, what does not, and what the context did not say.
2. Write a table comment for every table and a column comment for every column listed above,
   including the _dlt_* columns: the business definition first, then "Observed: ..." with what
   only the data shows (value lists with counts, ranges, null rates, uniqueness, relationships).
   Use the exact column names listed above.
3. Write the DDL for the semantic view {view}. Logical tables, primary keys and relationships:
{model}
   Put the business rule filters inside the metric expressions, add synonyms to every metric and
   dimension, verify every expression with a query, and put the business rules into
   AI_SQL_GENERATION. Do not create the view: the job creates it from your DDL.
4. Report in 5 to 10 lines what the data confirmed, what you added or changed, and why.

Return one JSON object with exactly these keys:
{{"report": [{{"kind": "confirmed" | "changed" | "added", "text": "..."}}],
  "table_comments": {{"TABLE": "..."}},
  "column_comments": {{"TABLE": {{"COLUMN": "..."}}}},
  "semantic_view_ddl": "CREATE OR REPLACE SEMANTIC VIEW {view} ..."}}
"""

FIX = """\
This semantic view DDL failed in Snowflake.

DDL:
{ddl}

Error:
{error}

Return one JSON object {{"semantic_view_ddl": "..."}} with the corrected DDL and nothing else.
"""


def _credentials() -> dict:
    """Return the Snowflake destination credentials from dlt secrets."""
    return dict(dlt.secrets["destination.snowflake.credentials"])


def _jwt(creds: dict) -> str:
    """Sign the short-lived key-pair JWT the Snowflake REST API accepts."""
    import jwt
    from cryptography.hazmat.primitives import serialization

    passphrase = creds.get("private_key_passphrase")
    key = serialization.load_pem_private_key(
        creds["private_key"].encode(), passphrase.encode() if passphrase else None
    )
    der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(der).digest()).decode()
    user = f"{creds['host'].split('.')[0].upper()}.{creds['username'].upper()}"
    now = int(time.time())
    claims = {"iss": f"{user}.{fingerprint}", "sub": user, "iat": now, "exp": now + 3540}
    return jwt.encode(claims, key, algorithm="RS256")


def _headers(creds: dict) -> dict:
    """Return the REST headers with key-pair JWT or PAT auth and the role."""
    if creds.get("private_key"):
        auth = {
            "Authorization": f"Bearer {_jwt(creds)}",
            "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
        }
    else:
        auth = {"Authorization": f"Bearer {creds['token']}"}
    headers = {"Content-Type": "application/json", "Accept": "application/json", **auth}
    if creds.get("role"):
        headers["X-Snowflake-Role"] = creds["role"]
    return headers


def _texts(node) -> list[str]:
    """Collect every text block from an agent response, in order."""
    found = []
    if isinstance(node, dict):
        if node.get("type") == "text" and isinstance(node.get("text"), str):
            found.append(node["text"])
        for value in node.values():
            found.extend(_texts(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_texts(item))
    return found


def _parse_json(text: str) -> dict:
    """Return the JSON object in the text, ignoring fences and prose."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError(f"agent answer is not JSON: {text[:500]}")
    return json.loads(text[start : end + 1])


def agent_run(prompt: str) -> dict:
    """Run an inline Cortex agent with the CoCo toolset and return its JSON."""
    creds = _credentials()
    url = f"https://{creds['host'].lower()}.snowflakecomputing.com/api/v2/cortex/agent:run"
    payload = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "models": {"orchestration": "auto"},
        "instructions": {"system": SYSTEM},
        "tools": [{"tool_spec": {"type": "code_toolset_all", "name": "code_toolset_all"}}],
        "tool_resources": {"code_toolset_all": {"permission_policy": {"type": "always_allow"}}},
        "stream": False,
    }
    resp = requests.post(url, headers=_headers(creds), json=payload, timeout=AGENT_TIMEOUT)
    resp.raise_for_status()
    texts = _texts(resp.json())
    if not texts:
        raise RuntimeError(f"agent returned no text: {resp.text[:500]}")
    return _parse_json(texts[-1])


def _data_tables(pipeline, tables: list[str] | None) -> list[str]:
    """Return the tables to annotate, without dlt and review tables."""
    names = tables or list(pipeline.default_schema.tables)
    return [n for n in names if not n.startswith("_dlt") and n != REVIEW_TABLE]


def _schema_hint(pipeline, tables: list[str]) -> str:
    """Describe the tables and columns as dlt knows them, one line per table."""
    lines = []
    for name in tables:
        table = pipeline.default_schema.tables[name]
        cols = ", ".join(
            f"{c} {spec.get('data_type', '')}".strip() for c, spec in table["columns"].items()
        )
        parent = f" (child of {table['parent']})" if table.get("parent") else ""
        lines.append(f"- {name.upper()}{parent}: {cols}")
    return "\n".join(lines)


def _model_hint(pipeline, tables: list[str], dataset: str) -> str:
    """Propose logical tables, keys and relationships from the dlt schema."""
    lines = []
    for name in tables:
        table = pipeline.default_schema.tables[name]
        if parent := table.get("parent"):
            lines.append(
                f"   - {name} AS {dataset}.{name.upper()}"
                f" PRIMARY KEY (_dlt_parent_id, _dlt_list_idx);"
                f" relationship {name} (_dlt_parent_id) REFERENCES {parent}"
            )
        else:
            lines.append(f"   - {name} AS {dataset}.{name.upper()} PRIMARY KEY (_dlt_id)")
    return "\n".join(lines)


def apply_comments(pipeline, client, tables: list[str], answer: dict) -> None:
    """Write the agent's comments for names the dlt schema knows."""
    for table in tables:
        fq = client.make_qualified_table_name(table)
        columns = {c.upper(): c for c in pipeline.default_schema.tables[table]["columns"]}
        if text := answer.get("table_comments", {}).get(table.upper()):
            client.execute_sql(f"COMMENT ON TABLE {fq} IS %s", text)
        written = 0
        for column, text in answer.get("column_comments", {}).get(table.upper(), {}).items():
            if column.upper() in columns and text:
                client.execute_sql(f"COMMENT ON COLUMN {fq}.{columns[column.upper()]} IS %s", text)
                written += 1
        print(f"  {table}: table comment, {written} of {len(columns)} column comments written")


def create_view(client, ddl: str, view: str) -> None:
    """Create the semantic view, asking the agent to fix the DDL on an error."""
    for attempt in range(DDL_RETRIES + 1):
        if "SEMANTIC VIEW" not in ddl.upper() or view.split(".")[-1].upper() not in ddl.upper():
            raise RuntimeError(f"agent did not return DDL for {view}: {ddl[:200]}")
        try:
            client.execute_sql(ddl)
            print(f"  {view}: created from the agent's DDL (attempt {attempt + 1})")
            return
        except Exception as ex:
            print(f"  {view}: DDL failed, {str(ex)[:200]}")
            if attempt == DDL_RETRIES:
                raise
            ddl = agent_run(FIX.format(ddl=ddl, error=str(ex)[:2000]))["semantic_view_ddl"]


def annotate(pipeline, business_context: str, tables: list[str] | None = None) -> dict:
    """Run the agent, then write the comments, the view and the review table."""
    pipeline.sync_destination()
    tables = _data_tables(pipeline, tables)
    with pipeline.sql_client() as client:
        dataset = client.fully_qualified_dataset_name(quote=False)
        view = f"{dataset}.{pipeline.dataset_name}{VIEW_SUFFIX}".upper()
        prompt = TASK.format(
            dataset=dataset,
            schema=_schema_hint(pipeline, tables),
            context=business_context.strip(),
            view=view,
            model=_model_hint(pipeline, tables, dataset),
        )
        print(f"-- Cortex agent on {dataset}: {len(tables)} tables")
        started = time.time()
        answer = agent_run(prompt)
        print(f"  agent answered after {time.time() - started:.0f}s")
        apply_comments(pipeline, client, tables, answer)
        create_view(client, answer["semantic_view_ddl"], view)
    for line in answer.get("report", []):
        print(f"  [{line.get('kind', 'note')}] {line.get('text', '')}")
    now = pendulum.now()
    rows = [
        {"kind": line.get("kind", "note"), "text": line.get("text", ""), "verified_at": now}
        for line in answer.get("report", [])
    ]
    review = dlt.resource(rows, name=REVIEW_TABLE, write_disposition="replace")
    info = pipeline.run(review)
    with pipeline.sql_client() as client:
        fq = client.make_qualified_table_name(REVIEW_TABLE)
        note = "What the Cortex agent confirmed, added or changed, checked against the data."
        client.execute_sql(f"COMMENT ON TABLE {fq} IS %s", note)
    print(f"  load {info.loads_ids[0]}: {len(rows)} review lines in {REVIEW_TABLE}, {view} ready")
    return answer
