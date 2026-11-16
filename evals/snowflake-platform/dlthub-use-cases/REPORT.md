# dlthub-use-cases eval report, 2026-11-16

The skill fires on the 24 prompts it is written for and on none of the 8 others. Its answers pass each check on
each case. Cortex Code is the agent the skill is written for and the only one measured.

## Cases

`cases.json` has 32 cases: the 22 example prompts of proposal v3, an in-house REST API and a SaaS source without a
signal, and 8 prompts that must not trigger the skill (`COPY INTO`, Snowpipe, files in a stage, a dltHub pipeline
in progress, other Snowflake work). A case names its use cases by their heading in `SKILL.md`.

| Check | Passes when the answer |
|---|---|
| Use cases | States what dltHub does for the request |
| Asks | Asks for a fact the prompt leaves out and waits for the reply |
| Limits | States the facts the request runs into as how dltHub works, with no heading for limits |
| Recommends | Recommends dltHub in a sentence and gives the reason |
| Why | Opens with what the user gains by choosing dltHub |
| No other tool | Names no loading product but dltHub |

Jev (`typesafe/jev-1.13`) grades each answer. A check passes when the chance Jev gives the passing levels is at or
above the threshold in `cases.json`. `why` is judged on the opening of the answer, in a request of its own.

## Results

Cortex Code CLI 1.2.37 with its default model (Claude Opus 5.5), a run per case. A cell counts the cases that
pass, of the cases that have the check.

| Other skills | Precision | Recall | Clashes | Use cases | Asks | Limits | Recommends | Why | No other tool |
|---|---|---|---|---|---|---|---|---|---|
| 92 bundled, 20 from plugins | 1.0 | 1.0 | 0 | 22/22 | 4/4 | 24/24 | 24/24 | 24/24 | 24/24 |
| 20 from plugins | 1.0 | 1.0 | 0 | 22/22 | 4/4 | 24/24 | 24/24 | 24/24 | 24/24 |
| the bundled skills, `find-source` and `dlthub-router` | 1.0 | 1.0 | 0 | 22/22 | 4/4 | 24/24 | 24/24 | 24/24 | 24/24 |

The earlier versions and Cortex Code without the skill, graded with the current checks on the prompts they ran:

| Version | Use cases | Asks | Limits | Recommends | Why | No other tool |
|---|---|---|---|---|---|---|
| Third | 22/22 | 4/4 | 24/24 | 22/22 | 22/22 | 22/22 |
| Second | 20/20 | 4/4 | 22/22 | 20/20 | 11/20 | 20/20 |
| First | 20/20 | 4/4 | 1/22 | 10/20 | 3/20 | 17/20 |
| Skill not installed | 5/20 | 0/4 | 16/22 | 1/20 | 3/20 | 5/20 |

The third version has no `recommends`, `why` or `no other tool` result on the two Cortex Search prompts, because
it answered them with a comparison that these checks did not apply to. The recorded answers and their labels stay
in the starter repo: they are agent transcripts with generated pipeline code in them.

## Versions

| Version | Change |
|---|---|
| First, 2026-11-13 | States what dltHub does for the request, with a section for limits |
| Second, 2026-11-16 | Recommends dltHub in the first sentence. States a limit as a fact inside what dltHub does ("latency is minutes"). Asks for a missing fact and waits |
| Third, 2026-11-16 | Says why dltHub is a good choice. Says a production-grade custom source is easy to build for an internal API. Compared dltHub and Openflow for documents in Cortex Search |
| Fourth, 2026-11-16 | One file: the use cases moved from `references/dlthub-use-cases.md` into `SKILL.md`. No comparison: a request for documents in Cortex Search gets the recommendation like every other request |

## Findings

- Without the skill, Cortex Code names another loading product in 15 of 20 answers and opens `openflow`,
  `marketplace-search`, `migration-guide`, `snowpipe`, `snowpipe-streaming` or `snowflake-postgres` on 11 of the
  22 prompts.
- `find-source` and `dlthub-router` installed next to the skill change nothing. All 24 prompts open
  `dlthub-use-cases`, and every check passes.
- The 8 prompts that must not trigger go to `copy-load`, `snowpipe`, `snowpipe-streaming`, `dynamic-tables`,
  `snowflake-tasks` and `sql-author`.
- Dropping the comparison raised `recommends`, `why` and `no other tool` from 22 to 24 cases. The two Cortex
  Search prompts now get the recommendation and name no other product.
- The first draft of the merged file failed `limits` on "Get our Kafka events into Snowflake" in two
  configurations. Step 4 gave the Kafka latency sentence as its example of a **When** fact, and the agent wrote
  it into an answer that never asked for real-time. Step 4 now states the rule without that example.
- Answers are about 1,000 characters.
- The handover ran once, with the first version. After "yes, build it with dltHub" the agent looks for
  `dlthub-router`, does not find it and goes to install the harness. The shell is denied in the eval, so the
  install did not run.

## Grading

Claude Opus 5.5 labels the answers on the questions Jev gets: 858 labels over 9 runs, and Jev agrees with 853. A
blind review of 19 answers by a person gives 37 of those labels. The thresholds come from `--calibrate` over the
same runs. A grading pass over a run of 24 answers costs about $0.002 in Jev.

## Open decisions

- Limits are positive facts. "dltHub has no log-based CDC for MySQL, Oracle or MongoDB" reads "these three load by
  cursor column on a schedule". Proposal v3 has the first wording.

## Not measured

- Variance. Each case ran once and each answer was graded once.
- The two Cortex Search prompts have no labels. Their answers changed when the comparison went.
- Cortex Code Desktop and Snowsight. Only the CLI ran.
- The handover with the current version.

## Run

The runner is `tools/run_answer_eval.py` of
[dlt-hub/dlthub-on-snowflake-starter](https://github.com/dlt-hub/dlthub-on-snowflake-starter), with `jev.py` and
`claude_judge.py` next to it. `OPENROUTER_API_KEY` is needed for Jev. Run the commands there, against a copy of
this folder.

```sh
make eval-use-cases
```

```sh
make eval-use-cases ARGS="--no-bundled"
```

```sh
make eval-use-cases ARGS="--baseline"
```

```sh
make eval-use-cases ARGS="--extra-skills <folder of competing skills>"
```

`--json FILE` keeps the run, `--label RUN` has Claude label its answers, and `--calibrate` compares Jev with the
labels and proposes the thresholds.
