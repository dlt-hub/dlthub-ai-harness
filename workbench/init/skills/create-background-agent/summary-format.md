# The shape of `summary`

This file owns how every background agent writes its `summary`, the default section sets, and how
the ids in it become links. The field itself is declared in
[agent-md-reference.md](agent-md-reference.md).

The platform renders `summary` as markdown on the run page, and it is the only field a reader sees
without opening the result. Every agent writes it the same way. Each agent's body states these
rules again under "Summary format", since the model reads the body and never this file, so a
change here is a change in every body that states them.

- **Markdown headings over short bullets, and nothing else.** No text before the first heading, no
  text outside a bullet, no question or bracketed note next to a heading.
- **The same headings on every run of one agent**, in the same order, named for what that agent
  reports. Take the default for the kind of agent below and change it where the agent reports
  something else. Declare the set in the body and hold to it.
- **The finding comes first and the scope last.** The first section says what the run found; what
  it covered goes at the bottom, next to the detail a reader opens from there.
- **One or two plain sentences per bullet, one fact each.** Two verbs joined by `and` or `then`
  are two bullets.
- **A part of a finding is a bullet under it, nested one level.** A grade's categories and a
  check's broken instructions sit inside the finding they belong to. Only `##` headings, so every
  heading is a section a reader can scan for.
- **What the run could not cover goes in `Scope`.** Checks that did not apply, inputs that could
  not be read, a window that was cut short. An agent with no `Scope` section puts them in its last
  section, which is what `job-inspector` does with `Confidence`.
- **A markdown table only as the last thing in the last section**, when the agent reports rows.
  Its headers are lowercase and name the field in the row. A row that measured nothing stays out;
  how many there were belongs in `Scope` or in the tally above the table. **No rows means no
  table**, and a sentence in its place saying what was not measured. A placeholder row, with
  `none` in the first cell and the rest empty, reads as a broken report.
- **Every run id and job ref is a link**, wherever it falls, in a summary the deployment
  linkifies. The text is the id in a code span. The target is
  `<web ui base>/w/<workspace id>/runs/<id>` for a plain job run,
  `/w/<workspace id>/agents/<job ref>/runs/<id>` for a run of an agent job, and `/jobs/<job ref>`
  for a job. `dlt_runtime.urls` builds the base from the API base url and its `job_run_url`
  writes the plain run route for every run alike, so an agent run is moved onto the agent route
  by the caller, the only side that knows which job a run id belongs to.
- **Markdown only, no raw HTML.** The summary renderer in the web UI strips tags, so a `<details>`
  element folding a long list arrives as an empty section. A long list goes in as plain bullets.
- **Close every code span, and never escape a backtick with a backslash.** An unbalanced span
  swallows the rest of the line in the UI, and a backslash in front of a backtick renders as
  itself.
- **Plain language, none of the register a model falls into.** A summary is read by an engineer
  deciding what to do, so it states facts in the words the workspace uses. These shapes stay
  out, and the body of every agent names them:

  | out | in |
  |---|---|
  | `Nothing is owed`, `No action is required` | the sentence that says why: `The load added no column a transformation reads` |
  | `It is worth noting`, `Importantly`, `Notably`, `Overall`, `In summary` | the fact, with no opener in front of it |
  | `successfully`, `seamlessly`, `robust`, `comprehensive`, `leverage`, `delve` | the verb that happened: `loaded`, `read`, `found` |
  | `I found`, `my analysis`, `as an AI` | the finding, with no narrator |
  | `appears to`, `seems to` where the evidence settles it | the claim, with the confidence field carrying the doubt |
  | `not X but Y`, `X, not Y` | what is the case, stated once |

- **Every claim cites the artifact behind it, in the bullet that makes the claim.** The artifact
  goes in parentheses at the end, written as the command or path the reader runs to open it:
  (`dlthub job runs logs <run id>` line 52), (`pipelines/github.py` line 16). Quote the words that
  settle the point rather than paraphrasing them, so the reader validates the finding from the
  summary alone. A claim resting on nothing the reader can open says so, in the section that
  carries the doubt: `Confidence` for `job-inspector`.
- **No verdict label at the top.** State what was found; `passed` and the other output fields
  carry the verdict.

State the shape in the body and check it. `job-inspector` has the rules under "Summary format".
A heading, a bullet and a code span are what data settles, so anything reading the summary
afterwards checks them without a model. An agent that assembles its summary in Python around the
loop splits what the model wrote into bullets itself.

## Default sections

An agent that investigates, inspects or analyses an entity in the workspace takes the sections
`job-inspector` writes:

| heading | the bullets answer |
|---|---|
| `## Diagnosis` | What happened, where, and why; the bullet that carries the cause quotes its evidence with the source and the line |
| `## Recommendation` | What the reader does next: the target and the change, written as the instruction itself |
| `## Confidence` | What this rests on and what it leaves open; when nothing was left open, one bullet says so |

## Linking the runs and jobs a summary names

An agent writes a run id as a uuid, because that is what a person pastes into `dlthub job runs
logs`. It cannot write a link: its `run_context` carries the trigger, the run id and the interval,
and no workspace id or UI base. The ids become links after the loop, in the agent folder's
`agent.py`. dltHub runs its hooks around the loop of every job referencing the agent,
`validate_input(inputs)` before and `validate_output(output)` after, so a declared
`run.agent("<ref>", ...)` gets the links as much as a decorated one.

```python
from .links import link_summary


def validate_output(output: Dict[str, Any]) -> Dict[str, Any]:
    return link_summary(output)
```

`links.py` beside it does the work: `linkify` writes each id as a link, and
`labels_from_platform` reads the run number behind it and makes it the link text, so a reader
meets `#114` rather than a uuid. The inspector's folder holds both files. An agent folder imports
only its own files, so an agent elsewhere copies `links.py` beside its own definition and calls it
from its own `agent.py`.

A span holding an id becomes the text of the link, since a link wrapped around a code span renders
and a link written inside one prints its markup. So the inspector's
`` `dlthub job runs logs <id>` `` is what the reader clicks.

**Only ids that resolve belong in a summary.** Every uuid in it becomes a link to a job run page,
so a pipeline run id, a load id or a package id points at a page that does not exist. Name the
pipeline by its name and the load by its step, and write the job run id.

`linkify` writes the plain run route for every id alike. A run of an agent job has its page under
`/agents/<job ref>/runs/<id>`, and only the code holding that job ref can move the link there, so
an agent whose summary names another agent's runs writes that step itself.
