# Toolkits in Cortex Code

Cortex Code reads the skill list and `CORTEX.md` once, when the session starts. Skills and rules that arrive later
are on disk, but not in your skill list and not in your rules. Read them from disk.

1. **After something new is installed, read again.** This applies after `dlthub ai toolkit install`, after new
   folders appear in `.cortex/skills/` or new rules in `.cortex/rules/`, or when the user says that skills or
   rules changed:
   - List `.cortex/skills/` and compare it with your skill list. For each skill that is not in your list, read
     the frontmatter of `.cortex/skills/<name>/SKILL.md` (its name and description).
   - Run `make cortex-md-check`. When it says the section is out of date, run `make cortex-md`: it rewrites only the
     dltHub rules section of `CORTEX.md`.
   - Read `CORTEX.md` again, from `# dltHub CoCo Pipeline Builder rules` to the next top-level heading, and follow
     the new rules from now on.
   - Tell the user in one line which skills and rules are new, and that a new session lists them as skills.
2. **A skill on disk is usable now.** When a rule, a handover or the user names a skill that is not in your list,
   read `.cortex/skills/<name>/SKILL.md` and follow it, with the reference files next to it. Do this before you
   say that a skill does not exist.
3. **Check where an install writes.** `dlthub ai toolkit install` prints the files it wrote. Read the entry skill
   and the workflow rule from those paths. When they are not under `.cortex/`, a new Cortex Code session does not
   load them either: tell the user.
4. **Do not reinstall** a toolkit whose skills are in `.cortex/skills/` only because they are missing from your
   skill list.
