---
name: review-pr
description: Review a pull request against dltHub AI Workbench standards. Use when reviewing a PR, checking skill or workflow quality, auditing toolkit changes, or preparing a PR for merge. Covers architectural clarity, product principles alignment, skill format, workflow correctness, and iterative design.
argument-hint: "[pr-number]"
---

# Review PR

Review a pull request against the quality standards of this repo. Gather data in parallel where possible.

Parse `$ARGUMENTS`: the PR number or URL is `PR_ID`. Everything after `--` is **reviewer instructions** (optional focus areas).

## Prerequisites

- GitHub CLI (`gh`) is authenticated
- `make validate-toolkits` is available

---

## Step 1 — Fetch PR metadata and diff (in parallel)

```bash
gh pr view [pr-number] --json title,body,author,state,baseRefName,headRefName,number,url,comments,reviews,labels
gh pr diff [pr-number]
```

Extract any issue references from the PR body (`fixes #N`, `closes #N`, `#N`) and fetch each:

```bash
gh issue view <number> --json title,body,author,state,comments,labels
```

Understand the original problem being solved before evaluating the solution. Identify which toolkits, skills, commands, rules, or workflows are changed.

---

## Step 2 — Run automated validation

```bash
make validate-toolkits
```

Report failures immediately — broken frontmatter, unresolved skill references, marketplace inconsistencies, wrong argument-hint format, rule files with frontmatter. These are blocking.

---

## Step 3 — Review against product principles

Evaluate the change against each principle from `product_principles.md`:

### Principle 1: Transparent, declarative, context-aware

- [ ] No black-box abstractions — the agent's steps are visible and inspectable
- [ ] Intermediate outputs are persisted as readable artifacts (Markdown, DBML, SQL, annotated Python)
- [ ] Each step produces something the user can review before the next step begins
- [ ] Context flows forward: source metadata, schemas, annotations are not discarded
- [ ] Logs and traces are available; agents don't silently consume data

> "Un-black-box the process." A skill that conflates distinct stages hides intent. Split them — each conceptual stage must be its own step with its own inspectable, persisted output.

### Principle 2: Modular, composable

- [ ] Uses dlt built-ins (auth helpers, REST client, dataset API) rather than reimplementing patterns
- [ ] New functionality is a discrete skill or command, not woven into an existing one
- [ ] Workflow references are well-structured: internal links use `` `(skill-name)` ``, external toolkit handoffs use `**toolkit-name**`
- [ ] No new library dependencies unless necessary — prefer dlt ecosystem (ibis, marimo, Streamlit)

### Principle 3: Built-in guardrails, human-in-the-loop

- [ ] Skills ask for user input before irreversible or data-modifying steps
- [ ] Sample/preview before full execution: `.add_limit(1)`, `dev_mode=True`, schema preview before pipeline run
- [ ] Secrets never appear in agent output — only via redacted CLI or MCP inspection tools
- [ ] Agents don't auto-proceed past defined checkpoints (code review, schema validation, deployment approval)

### dltHub AI workbench approach for building skills
- [ ] Skills should not merely contain docs but be step by step instructions for workflows for the agent
- [ ] Ensure a skill gives clear and consise instructions for the workflow and not just copy the docs into 

---

## Step 4 — Core library gaps: prefer upstream fixes, flag workarounds

The workbench may introduce temporary workarounds solving a problem via a skill that can actually be solved deterministically e.g via a CLI command or a platform capability. These workarounds may address gaps in [dlt](https://github.com/dlt-hub/dlt) or [dltHub](https://github.com/dlt-hub/dlthub) temporarily, but they should always be visible, flagged to core maintainers, and have a clear path to removal.

**Prefer deterministic over probabilistic.** If something can be handled by a CLI command in [dlt](https://dlthub.com/docs/hub/command-line-interface) or [dltHub](https://dlthub.com/docs/reference/command-line-interface), a library call, or a platform feature — that is always preferable to a skill-based workaround. An agent skill is a last resort, not a first option, when the core library could own the behaviour.

**Check for these patterns:**

- [ ] Is there a dlt or dlthub built-in (pagination, auth, schema inference, secrets, normalisation) that should be used instead of skill-level instructions?
- [ ] If no built-in exists but one clearly should — could this be proposed as a new feature in [dlt](https://github.com/dlt-hub/dlt) or [dltHub](https://github.com/dlt-hub/dlthub)? A skill encoding something deterministic is a signal the core library has a gap worth filing.
- [ ] If a workaround exists, is it marked with a `TODO: remove when dlt#<issue> / dlthub#<issue> is resolved` comment so it has an expiry?
- [ ] Is the upstream gap tracked as an issue in the right repo?
  - ingstion library gap → [github.com/dlt-hub/dlt](https://github.com/dlt-hub/dlt)
  - transformations or data quality libraries gap → [github.com/dlt-hub/dlthub](https://github.com/dlt-hub/dlthub)
  - platform gap → [github.com/dlt-hub/runtime](https://github.com/dlt-hub/runtime)
- [ ] Is the workaround scoped as narrowly as possible, so it doesn't leak into unrelated skills?

**What to flag in the review:**

If a skill reimplements something the core library handles (or should handle), note it — not as a blocker, but as a signal that either (a) the skill should defer to the built-in, or (b) an upstream issue should be opened and a `TODO` added. The goal is that workarounds are visible and temporary, not silently normalised into the workbench.

---

## Step 5 — Architecture and separation of concerns

The most common source of review feedback.

**For each changed skill or workflow step:**

1. **Does it do one thing?** Conflating conceptual stages is a red flag.
   - Bad: a single step builds glossary + CDM + source mappings + SQL in one pass
   - Good: annotate-sources → create-ontology → generate-cdm → create-transformation

2. **Are the outputs explicit?** Each step must produce something tangible and persisted:
   - Glossary/taxonomy → Markdown files
   - Data model → DBML schema
   - Source mappings → annotated dlt Python sources with decorators
   - Transformations → SQL files (ANSI SQL preferred) or IBIS Python

3. **Is the scope bounded?** Glossary and taxonomy are scoped to concepts actually found in workspace sources — not speculative. CDM starts relational (DBML), not analytical (Kimball), until explicitly warranted.

4. **Is the sequence correct?**
   - Conceptual definitions (glossary, taxonomy, ontology) before data models
   - Relational CDM before dimensional/analytical model
   - Source → CDM mapping is separate from the CDM definition itself
   - Transformations built on top of an established CDM, not reinvented per query

---

## Step 6 — Skill format and trigger quality

For any changed SKILL.md files:

**Frontmatter:**
- [ ] `name` matches directory name exactly
- [ ] `description` contains use-when patterns (not "does X" — should name trigger conditions)
- [ ] `argument-hint` tokens use `[bracket]` convention (not `<angle>` or bare text)

**Trigger quality:**
- [ ] Description triggers for the right user queries
- [ ] Does NOT trigger for unrelated queries — check against other skill descriptions for clashes
- [ ] If multiple skills could trigger, the workflow rule disambiguates

**Content:**
- [ ] Prerequisites listed at top
- [ ] Steps are numbered and sequential
- [ ] **Concise** — every sentence earns its place. Flag redundant preamble, restated context, over-explained obvious steps, and padding. A shorter skill is a better skill.
- [ ] Authoritative doc links embedded (dlt docs, API provider docs, dltHub platform docs)
- [ ] Code examples are minimal and correct (3–10 lines; no fabricated output)
- [ ] Handoff conditions to the next skill are explicit

---

## Step 7 — Workflow and handoff correctness

For changes to `workflow.md` or `rules/`:

- [ ] `## Workflow Entry` present and references the correct entry skill
- [ ] `## Core workflow` uses numbered steps with `` `(skill-name)` `` links
- [ ] All `` `(skill-name)` `` references resolve to real skill directories
- [ ] `## Handover to other toolkits` uses `**toolkit-name**` (bold) with trigger condition + originating skill
- [ ] Handover toolkit names exist in `marketplace.json`
- [ ] `toolkit.json` `workflow_entry_skill` matches the entry skill declared in `workflow.md`
- [ ] No rules files contain YAML frontmatter (rules are catch-all, no frontmatter)

---

## Step 7a — Cross-toolkit link symmetry

Every toolkit that sends users somewhere must also be reachable from somewhere. Check both directions for any affected toolkit.

**Outgoing links** (this toolkit → other toolkits):

- [ ] Each outgoing handover names the target toolkit, the specific entry skill (`find-source`, `new-endpoint`, etc.), and the trigger condition that causes the handoff
- [ ] The named target skill actually exists in the target toolkit

**Incoming links** (other toolkits → this toolkit):

- [ ] The `workflow.md` has an `### Incoming` subsection listing every toolkit that can arrive here
- [ ] Each incoming entry names the originating toolkit + skill, and specifies what context is already established on arrival (e.g. "pipeline name and dataset are known — skip `list_pipelines` discovery")
- [ ] Incoming context assumptions are reflected in the entry skill itself (it should skip steps it doesn't need to redo)

**Cross-check symmetry** — for every outgoing handover declared in toolkit A, verify that toolkit B's `workflow.md` has a matching incoming entry, and vice versa:

```bash
# Quick grep across all workflow.md files
grep -r "Incoming\|Outgoing" workbench/*/rules/workflow.md
```

Flag any broken pair: A says it sends to B, but B has no incoming entry for A, or the skill name referenced doesn't exist.

---

## Step 8 — Format and naming conventions

| Artifact | Expected format |
|---|---|
| Data models | DBML (not raw SQL DDL, not ERD images) |
| Transformations | ANSI SQL preferred; IBIS Python as fallback |
| Annotated sources | Python with dlt decorators (`@dlt.resource`, `@dlt.source`) |
| Human-readable definitions | Markdown files (`.md`) |
| Config / metadata | YAML |
| Secrets | Never in output; via `dlt --redacted secrets list` or MCP |

- [ ] Format choices match table above
- [ ] SQL uses ANSI syntax, not destination-specific dialects (unless PR explicitly targets one)
- [ ] Python uses dlt built-ins for auth, pagination, REST client

---

## Step 9 — README currency

Check whether the PR's changes affect anything described in `README.md` (root) or a toolkit-level `README.md`:

- [ ] New toolkit added → listed in the root README
- [ ] Toolkit renamed or removed → README updated accordingly
- [ ] New skill or command added that changes what a toolkit does or how it's used → toolkit README reflects it
- [ ] Workflow entry point changed → README "how to start" instructions still accurate
- [ ] Installation or dependency changes → README setup steps still valid

If README updates are missing, flag as required — not a suggestion.

---

## Step 9a — dlt docs currency

The dltHub AI Workbench is documented in the dlt docs under [`dlt-ecosystem/llm-tooling`](https://github.com/dlt-hub/dlt/tree/devel/docs/website/docs/dlt-ecosystem/llm-tooling). Two pages cover the workbench directly:

- **`llm-native-workflow.md`** — REST API pipeline toolkit: skill names, seven-phase workflow, setup instructions, validation checklist, handoff possibilities
- **`explore-and-transform.md`** — Data exploration and transformations toolkits: skill names, intent levels, four-stage transformation process, setup, deliverables

Check whether the PR's changes affect anything described on those pages:

- [ ] Skill renamed, added, or removed → command references in the docs are still accurate
- [ ] Workflow sequence or phase changed → numbered steps in the docs still match
- [ ] Setup or installation requirements changed → setup instructions still valid
- [ ] Handoff conditions or target toolkits changed → "extended capabilities" / next steps section still accurate
- [ ] Transformation stages changed (annotate → ontology → CDM → transformation) → `explore-and-transform.md` reflects the current sequence

Docs live in a separate repo ([dlt-hub/dlt](https://github.com/dlt-hub/dlt)). If updates are needed, flag them as a required follow-up — either in this PR (if the author has access) or as a tracked issue.

---

## Step 10 — Compose the review

**No prose.** Every line must be a bullet, label, or checklist item. No explanatory paragraphs, no filler sentences. If something needs context, add it as a sub-bullet.

```
## Summary
- <one-line: what changed> — <one-line: why>

## Required changes
- [Bug] <file:line> — <what's wrong> → <fix>
- [Conciseness] <skill/section> — <what to trim>
- [Workaround] <what it does> — file upstream: <repo> → add TODO comment
- [Architecture] <issue>
- [Workflow] <issue>

## Suggestions
- <suggestion>

## Checklist
- [ ] make validate-toolkits passes
- [ ] Core gaps flagged upstream; workarounds marked with TODO + issue link
- [ ] Principle 1: transparent outputs, no black boxes
- [ ] Principle 2: uses dlt built-ins, modular
- [ ] Principle 3: human checkpoints, no auto-proceed
- [ ] Steps separated by concern, explicit artifacts
- [ ] Skill descriptions trigger correctly, no clashes
- [ ] Workflow references resolve
- [ ] Cross-toolkit links are symmetric (outgoing in A ↔ incoming in B)
- [ ] Incoming context assumptions reflected in entry skill behaviour
- [ ] README updated if toolkit structure, entry points, or usage changed
- [ ] dlt docs (`llm-tooling`) updated or follow-up tracked if skill names/workflow changed
- [ ] Authoritative doc links embedded

## Verdict
APPROVE / REQUEST CHANGES / COMMENT
```

Post the review — pass the body as a single quoted string directly (heredoc syntax breaks in zsh):

```bash
gh pr review [pr-number] --request-changes --body "## Summary
- ...

## Required changes
- ..."

gh pr review [pr-number] --approve --body "..."
gh pr review [pr-number] --comment --body "..."
```

---

## Common patterns from past reviews

**Conflating steps (most frequent architectural issue):**
> A skill produced glossary + CDM + source mappings in a single step. Fix: split into annotate-sources → create-ontology → generate-cdm, each with a distinct persisted artifact.

**Workaround silently absorbed into a skill:**
> A skill manually constructed pagination logic because "dlt's REST client didn't support X" — with no upstream issue filed and no TODO marking it temporary. Fix: open an issue in dlt-hub/dlt, add a `TODO: remove when dlt#<issue> is resolved` comment, and scope the workaround as narrowly as possible.

**Over-scoped glossary:**
> Glossary included domain concepts not present in any loaded source. Fix: scope to concepts actually found in workspace data.

**IBIS over SQL for transformations:**
> Early versions preferred IBIS; LLMs perform better with SQL and it's more readable. Use ANSI SQL; IBIS is an acceptable fallback.

**Missing human checkpoint before pipeline run:**
> Skills ran the full pipeline without asking the user to review generated code. Fix: always show generated code, get approval, then run with `.add_limit(1)` on first execution.

**Skill description too generic:**
> "Handles transformation workflows" won't trigger reliably. Fix: use explicit use-when language with concrete user intent examples.

**Workflow handoff missing originating skill:**
> Handover listed the target toolkit but not which local skill the user was in. Fix: add "from (`skill-name`) when…" context.
