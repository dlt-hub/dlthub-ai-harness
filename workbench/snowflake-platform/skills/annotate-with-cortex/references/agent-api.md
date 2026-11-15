# Cortex Agents REST API, as used from a dlt job

## The call

`POST https://<account>.snowflakecomputing.com/api/v2/cortex/agent:run`, inline agent, no
`CREATE AGENT` needed. `<account>` is the dlt `host` value lower-cased (`myorg-myaccount`).

```json
{
  "messages": [{"role": "user", "content": [{"type": "text", "text": "<prompt>"}]}],
  "models": {"orchestration": "auto"},
  "instructions": {"system": "<system prompt>"},
  "tools": [{"tool_spec": {"type": "code_toolset_all", "name": "code_toolset_all"}}],
  "tool_resources": {"code_toolset_all": {"permission_policy": {"type": "always_allow"}}},
  "stream": false
}
```

- `code_toolset_all` is the Coding Agent toolset, "backed by the same runtime that powers CoCo":
  `bash`, `read`, `write`, `edit`, `grep`, `glob`, `web_search`, `snowflake_sql_execute`, `skill`.
  No `tool_resources` entry beyond the permission policy is needed.
- `permission_policy: always_allow` is required for unattended callers (jobs, tasks, procedures):
  the default `always_ask` would stop at the first state-changing tool call and nobody can answer.
  Under `always_allow` the agent runs any command its role can reach, so use the least-privileged
  role that still reads the dataset.
- `snowflake_sql_execute` in the sandbox is documented as read-only: `SELECT`, `SHOW`, writes to
  stages. The agent profiles; the job writes. Do not design around the agent issuing DDL.
- `stream: false` returns one JSON document instead of server-sent events. Simpler to parse; the
  text answer is in `content` items of type `text`, possibly several (the last one is the final
  answer). `_texts()` in the template walks the whole response for them.
- Default timeout is 15 minutes for the whole run. `background: true` allows 6 hours but needs a
  thread and polling; not needed for a handful of tables. Keep the requests timeout at or above the
  expected run (900 s in the template).
- `models.orchestration: "auto"` lets Snowflake pick; a fixed model such as `claude-sonnet-4-6`
  works too but availability differs per region (`CORTEX_ENABLED_CROSS_REGION` may be needed).

## Auth, reusing the dlt destination credentials

Key pair (preferred, no expiry, no network policy):

```python
import jwt  # PyJWT
from cryptography.hazmat.primitives import serialization

key = serialization.load_pem_private_key(private_key_pem.encode(), None)
der = key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(der).digest()).decode()
user = f"{ACCOUNT.upper()}.{USER.upper()}"          # ACCOUNT = host before the first dot
claims = {"iss": f"{user}.{fingerprint}", "sub": user, "iat": now, "exp": now + 3540}
token = jwt.encode(claims, key, algorithm="RS256")
headers = {"Authorization": f"Bearer {token}", "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT"}
```

PAT: `Authorization: Bearer <token>`, no extra header. PATs expire and usually need a network
policy. `X-Snowflake-Role: <role>` selects the role for the call; the role needs
`SNOWFLAKE.CORTEX_USER` or `SNOWFLAKE.CORTEX_AGENT_USER`.

Read the values with `dlt.secrets["destination.snowflake.credentials"]`, never from the TOML file,
so that the same code works locally and on dltHub where secrets come from the platform store.

## Response handling

- Collect every `{"type": "text", "text": ...}` block; take the last.
- The model sometimes wraps the JSON in a fence or adds a sentence. Slice from the first `{` to the
  last `}` and `json.loads` that.
- Validate before applying: comments only for columns the dlt schema has (compare upper-cased),
  DDL must contain `SEMANTIC VIEW` and the view name. On a DDL error, send the DDL and the error
  back in a second call asking for corrected DDL only; two retries is enough in practice.
- Log the report lines; they are the demo-worthy part (test rows that distort totals, time-zone
  month shifts, codes without meaning, stale comments).

## Alternatives, and when they fit better

- `SNOWFLAKE.CORTEX.AGENT_RUN(<request json>)` from SQL: the same body, callable from a Snowflake
  task or procedure. Fits when the schedule should live in Snowflake, not in dltHub.
- A `CREATE AGENT` object with `generic` tools backed by stored procedures: the documented path
  if the agent itself should write (the procedure does the DDL). More objects to maintain.
- `cortex exec` (the CoCo CLI, headless) or the Cortex Code Agent SDK: CoCo proper, with its SQL
  tool allowed to write when pre-approved. Needs the CLI installed in the job image and a
  connections.toml; untested inside dltHub jobs as of Nov 2026.
