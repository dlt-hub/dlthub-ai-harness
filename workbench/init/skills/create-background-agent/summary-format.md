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
  how many there were belongs in `Scope` or in the tally above the table.
- **Every run id and job ref is a link**, wherever it falls. The text is the id in a code span and
  the target is `<web ui base>/w/<workspace id>/runs/<id>` for a run, `/jobs/<job ref>` for a job.
  `dlt_runtime.urls` builds that base from the API base url, which is how the CLI prints a run
  link.
- **Markdown only, no raw HTML.** The summary renderer in the web UI strips tags, so a `<details>`
  element folding a long list arrives as an empty section. A long list goes in as plain bullets.
- **Close every code span, and never escape a backtick with a backslash.** An unbalanced span
  swallows the rest of the line in the UI, and a backslash in front of a backtick renders as
  itself.
- **No verdict label at the top.** State what was found; `passed` and the other output fields
  carry the verdict.

State the shape in the body and check it. `job-inspector` has the rules under "Summary format",
and `job-inspector-eval` grades them with `summary_has_required_sections`,
`summary_sections_are_bullets`, `summary_code_spans_balanced` and `summary_within_length`. An
agent that assembles its summary in Python around the loop splits what the model wrote into
bullets itself.

## Default sections

An agent that investigates, inspects or analyses an entity in the workspace takes the sections
`job-inspector` writes:

| heading | the bullets answer |
|---|---|
| `## Diagnosis` | What happened, where, and why; the bullet that carries the cause quotes its evidence with the source and the line |
| `## Recommendation` | What the reader does next: the target and the change, written as the instruction itself |
| `## Confidence` | What this rests on and what it leaves open; when nothing was left open, one bullet says so |

An agent that grades another agent's run takes the sections `job-inspector-eval` writes, which
open on the verdict and keep the evidence underneath:

| heading | the bullets answer |
|---|---|
| `## Findings` | The counts, any rule broken that outranks the rest, what the graded agent got wrong and why it matters, then one bullet per category with its verdict and every broken check nested under it |
| `## Recommendation` | What to change in the graded agent's definition so a broken check stops recurring. A report over one run leaves this out, because a change to an agent's instructions rests on a pattern across runs |
| `## Scope` | How many checks did not apply, then the run or runs graded and what each acted on, each linked |
| `## Detailed evaluation results` | The tally, then the table of every decided check: `check_id`, `category`, `kind`, `results`, `reasoning` |

`job-inspector-eval` names its two categories `Instruction following` and `Quality`; a grader with
other categories renames those bullets and leaves the rest. A report over many runs takes the same
sections, with the window, the runs skipped and the reasons under `Scope`, and each broken
instruction states the runs it broke on.

Changing a section the evaluator grades means changing the evaluator too:
`REQUIRED_SUMMARY_SECTIONS` in its `checks.py` holds the inspector's three headings, and the
checks that read the `Confidence` section by name go with them.

## Linking the runs and jobs a summary names

An agent writes a run id as a uuid, because that is what a person pastes into `dlthub job runs
logs`. It cannot write a link: its `run_context` carries the trigger, the run id and the interval,
and no workspace id or UI base. So the ids become links after the loop, in `links.py` under
`agents/job-inspector/`. The inspector and the evaluator share that one module, so a run reads the
same way in both summaries.

```python
import importlib.util

# loaded by path under a name of its own: `links` is a common module name, and a `sys.path`
# entry pointing at the agent folder would shadow or be shadowed by another one
spec = importlib.util.spec_from_file_location(
    "dlthub_agent_links", ".claude/dlthub/agents/job-inspector/links.py"
)
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)

summary = output["summary"]
output["summary"] = links.linkify(
    summary, links.web_ui(), links.labels_from_platform(summary)
)
```

The evaluator loads the same file the same way, in `_shared_links` in its `checks.py`.

A span holding an id becomes the text of the link, since a link wrapped around a code span renders
and a link written inside one prints its markup. So the inspector's
`` `dlthub job runs logs <id>` `` is what the reader clicks. `labels_from_platform` reads the run
number behind each id and makes it the link text, so a reader meets `#114` rather than a uuid; the
evaluator passes `run_labels` instead, built from the runs it already holds. Wiring it needs the
decorated form in [deployment.md](deployment.md).
