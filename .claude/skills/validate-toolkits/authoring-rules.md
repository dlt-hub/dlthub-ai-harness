# Authoring rules

Check each rule on the toolkits under review. `make validate-toolkits` checks some of them mechanically (noted
below): report its findings and check the rest by reading. Each rule lists mistakes that were made before.

## Rules (`rules/*.md`, loaded on every turn)

1. **A rule never repeats the procedure of a skill.** No skill steps, commands, checklists or intent → skill tables
   that restate skill descriptions. A rule may repeat a principle that a skill also applies, and it shows how the
   skills form a workflow.
   - Check: for each rule bullet, search the skills of the toolkit for the same steps, commands or checklists.
   - Seen: `dq-rules.md` restating `define-data-quality-checks`; a profiles rule repeating `setup-profiles`; an
     intent table in a routing rule restating the skill descriptions.
2. **Rules are composable.** A rule carries nothing that another toolkit adds when it is installed: other toolkits'
   folders, commands, skills or step numbers.
   - Check: a line that describes another toolkit belongs in that toolkit's rule.
   - Seen: the init rule describing platform toolkits; local-workspace saying "a platform toolkit may replace its
     steps 1–2"; `dq-rules.md` naming skills of other toolkits; a snowflake rule citing step numbers of
     `find-source` and `annotate-sources`.
3. **Rules say how to use toolkits, not how to write them.** Authoring conventions go to CLAUDE.md, TOOLKITS.md and
   the validator.
   - Check: a line that constrains authors ("write a new kind of artifact only to…", "other toolkits must…").
   - Seen: "write a new kind of artifact only to one of these locations" in the init rule.
4. **Handover bullets only for session context that the next toolkit expects.** A generic arrival ("the pipeline is
   known, skip discovery") is the "Handed over from another toolkit?" paragraph of the entry skill. A change of
   goal is the router's job.
   - Check: each Incoming or Outgoing bullet changes what the next skill does.
   - Seen: about 2,500 words of "pipeline name is known, skip discovery" across toolkits.
5. **An add-on toolkit has no workflow rule and no entry skill.** It only adds rules and skills to init, is
   unlisted (`listed: false`), and is in `_NON_WORKFLOW_TOOLKITS` of `tools/validate_toolkits.py`. Its rules never
   say "ALWAYS start with <skill>".
   - Seen: local-workspace's workflow rule ("ALWAYS start with define-and-debug-jobs") pulled production requests
     into job work in every workspace.

## Skills

6. **Descriptions: "Use when" first.** Shape: `Use when <user intents and symptoms, with keywords>. <one short
   capability sentence>. [Not for <near miss> (<sibling skill>).]`
   - Keywords cover what the user wants and what the user can do or types (tool names, file types, error strings).
   - No step list, no "This skill should be used when", no step numbers of other skills, rule names, internal status
     or paths the user would not type.
   - A boundary names a sibling that installs together and competes, never something no one would confuse.
   - One owner per trigger among the skills of an install set (a toolkit with init and its dependencies).
   - Target 400 chars; `make validate-toolkits` warns over 1024 (Codex drops the skill).
   - Keep the phrases that the trigger evals in `evals/<toolkit>/<skill>/` depend on.
   - Seen: explore-data and build-notebook narrating their steps with far-off exclusions; quick-start and the router
     both claiming "what can I do with dlthub"; debug-sql-database-pipeline losing "failed load jobs", so
     troubleshoot-pipeline-run took the query.
7. **Artifact locations.** Skills read and write artifacts only in `.dlthub/schemas/` (and `export/`),
   `.dlthub/ontology/<name>/`, `.dlthub/explorations/<name>/` and `.dlthub/<platform>/` (owned by that platform
   toolkit), and name the path. Throwaway scripts go to the system temp dir. `validate_artifact_locations` checks
   the folder names and retired paths.
   - Check also: a new kind of artifact goes to a standard location, and the skill names the path.
   - Seen: `.schema/`, `schemas/import`, `.dlthub/ontology/snowflake/`, `tools/get_<source>_schema.py` written into
     the workspace.
8. **Code paths are examples.** A concrete path for sources, pipelines or transformations reads "for example", or
   the skill asks the user. transformations keeps `transformations/` as its default.
   - Seen: `tools/dq_run.py` and `pipelines/…` written as fixed locations.

## Platform toolkits

9. **Labels, and generic toolkits name no platform.** A platform toolkit's description starts with
   `Platform toolkit (<platform>):` (plugin.json and marketplace.json). A toolkit that works only with one platform
   ends with `Requires <platform> Platform.`. Generic toolkits never name a platform, its toolkits or skills, never
   run prefixed platform commands (`dlthub deploy`), never install `dlt[hub]` or `dlthub-client`, and write
   `deploy`, `job run`, `job logs` without a prefix. No toolkit depends on a platform toolkit.
   `validate_platform_agnostic` checks most of it.
10. **Platform toolkits never repeat local-workspace.** Every platform toolkit sets
    `workflow_entry_skill: prepare-deployment`, and its workflow rule opens with it. A platform skill holds no job
    declaration steps, trigger syntax, production-script checklist (dev_mode, dev limits, write_disposition, pinned
    dependencies) or local run steps: it points to `define-and-debug-jobs` or `prepare-deployment`. What differs on
    the platform (for example how the `prod` profile is made) is named in the platform's own rule.
    - Seen: both deploy skills carried the production-script checklist and trigger examples; the two entries checked
      different things.

## Destination toolkits

11. **Destination work goes to the destination toolkit, deployment to the platform toolkit.** A destination toolkit
    (`Destination toolkit (<destination>):`) owns loading into one destination and its ecosystem: the connection, the
    business context, the semantic layer, the destination's own tables, the destination's own agent. Visible to every
    agent; agent-specific parts are `components`. It depends on `init` only and never names a platform toolkit;
    only the platform toolkit of its destination depends on it. Generic toolkits never name it: where a destination
    is chosen, configured, troubleshot or modeled, they ask for "the destination toolkit" of the destination. The
    router description names every destination that has one. `validate_destination_agnostic` and
    `validate_index_drift` check most of it.
    - Seen: semantic views, connections and the Cortex Code rule inside `snowflake-platform`, which other agents
      never see; the destination skills pointing back to deploy skills.
12. **The destination's own agent is a handover.** Outside that agent, offer the task to it and, on yes, run it as a
    subagent with a brief of the task and its context (`delegate-to-cortex-code`), read-only by default. Never tell
    the user to switch agents and stop.

## Renames

13. **After a rename, every reference follows.** The validator resolves `(`name`)` refs in workflow rules only.
    Grep every file of every toolkit, the agent definitions, `evals/` and the starter's `.cortex` links for the old
    name.
    - Seen: `run-local-jobs` left in `deploy-workspace` and `debug-deployment` after the rename to
      `define-and-debug-jobs`.
