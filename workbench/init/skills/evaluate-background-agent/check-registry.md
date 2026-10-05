# Checks, the rubric and what a run reports

This file owns the checks an evaluator runs: one per instruction, the split between Python and the
judge, the rubric, and what the finished evaluation reports. The deployments are in
[evaluator-deployment.md](evaluator-deployment.md).

## One check per instruction

An instruction with two conditions becomes two checks, so a `FALSE` names one thing to fix.
Outcomes are `TRUE`, `FALSE` and `N/A`, each with a reasoning. `N/A` means the check's condition
did not apply to this run.

A check entry carries:

- **an id**, the one name the rubric, the registry and the summary all use;
- **a kind**: deterministic, judge, or hybrid, where Python decides and the judge explains;
- **a category**, which section of the summary reports it and which verdict it counts towards;
- **a security flag**, which outranks the counts in the verdict table below;
- **a precondition** on a judge check: the reason this run does not meet the check's condition.
  Python answers `N/A` itself, so the check never reaches the judge, its rubric stays out of the
  prompt, and the model spends no output saying the condition did not apply.

The registry is the one list of ids. A deterministic check's rubric is its docstring, and the
first paragraph of that docstring is the instruction it grades, which is the sentence the summary
reports. A judge check's rubric is an entry in the evaluator's body.

## Python decides what data settles

A registry of check functions over the graded run's output, trace and transcript. The same
functions extract the bounded evidence the judge reads, so the model never sees a whole log.

Python settles the profile off the run record, the tools the trace recorded, the headings and code
spans in the summary, whether a declared field is present at all, whether a cited line number
holds the text quoted beside it, and how many distinct runs the transcript read.

The judge answers whether a diagnosis names a cause rather than a symptom, whether a
recommendation names a target and a change, whether an excerpt supports the claim above it, and
whether a confidence statement matches what was left open.

## The rubric

The rubric is the body of the evaluator's `AGENT.md`, one entry per judge check: the instruction,
the window to read, and what makes it `TRUE`, `FALSE` or `N/A`. Render only the applicable entries
into the prompt. A rubric carries no `{{ }}` placeholder of its own: dlt renders the body once, so
one inside an injected value reaches the model raw.

The body states that the graded agent's text is content under evaluation and never an instruction
to follow, and delimits it as such.

## What the checks cannot see

- **Verbosity 0 hides the transcript from its checks.** A check that reads tool arguments or the
  agent's own statements needs the graded job's log at `agent.verbosity` 1. At 0 the log keeps
  tool names only, and those checks report `N/A` and say why. Keep an agent under evaluation at
  verbosity 1.
- **Line numbers run over the whole log.** The platform numbers `setup`, `program`, `runner` and
  `provider` lines in one sequence, so a job whose image build printed 197 lines has its first
  program line at 198. Evidence cites that number, and a check comparing an excerpt to its line
  counts the same way.
- **Judge checks are not deterministic.** Their accuracy was established on real runs rather than
  against a labelled set. A judge check that flips on the same input is a bug in its rubric; file
  it.
- **The judge reads model-authored text.** The body delimits it as content under evaluation and
  forbids following instructions found in it, which reduces the risk of prompt injection through a
  failed run's log rather than removing it.

Two more blind spots sit in the code that raises them: a transcript parser that read nothing while
the trace records tool use is a parser fault, and the stored job result needs a recent enough
`dlthub-client`. Each one belongs in the docstring of the function that detects it, in the
evaluator's own `checks.py`.

## What an evaluation reports

The results table holds one row per decided check, and over a window one row per check with how
it came back across the runs. A check that answered `N/A` on every run of the window has no row,
and a report that decided nothing writes no table and a sentence saying so, since a placeholder
row reads as a broken report.

`passed` is true when no check is FALSE, every open check came back answered, and at least one
check was decided. A judge response that is empty or cut off leaves checks unanswered and fails
the evaluation. `pass_rate` is `TRUE / (TRUE + FALSE)`, so `N/A` never moves it. It sits beside
`decided_count` and `na_count` in the summary, because a rate over a third of the checks reads the
same as a rate over all of them.

Constrained decoding guarantees the schema, not that a model fills it as declared. `checks` has
come back as a JSON string, so the reader also accepts a double encoding, a `{"checks": ...}`
wrapper, a map keyed by check id, per-entry serialisation and a trailing comma. A shape it cannot
read is named in the summary and fails the evaluation, rather than passing on the deterministic
results alone.

A category verdict counts the checks that broke when one run is graded and takes their share over
a window, because one run decides tens of checks and a window thousands:

| verdict | one evaluation | a window |
|---|---|---|
| blocking | a security check came back FALSE, or 6 or more checks broke | a security check came back FALSE, or over 10% broke |
| needs attention | 3 to 5 broke | 2% to 10% broke |
| minor issues | 1 or 2 broke | under 2% broke |
| no findings | none broke, and at least one was decided | the same |
| not graded | the category decided nothing | the same |

The summary sections a grader writes are in `summary-format.md` beside
(`create-background-agent`), next to the sections an inspecting agent writes.
