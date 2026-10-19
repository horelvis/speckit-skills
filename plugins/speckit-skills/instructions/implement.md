# speckit-skills: execution mode for this /speckit-implement run

The speckit-skills plugin is active in this project. From the implement command, keep:
prerequisites, checklist gate, loading context, ignore-file setup, extension hooks and the
final completion validation. REPLACE its task execution steps (parse tasks, phase-by-phase
execution, execution rules, progress tracking) with the loop below. Where the command talks
about executing tasks one by one or marking checkboxes yourself, this loop wins.

You are the orchestrator. You are the only one who changes tasks.md, and only through `mark`.

## Before the loop

Run `{{SW}} plan <FEATURE_DIR>/tasks.md --write --markdown`.
- Exit 1: STOP. Show the errors (usually a skill no longer installed or a broken dependency)
  and suggest fixing tasks.md or re-running /speckit-tasks. Do not implement an invalid plan.
- If no task has a `(skill: ...)` annotation, tell the user tasks.md predates the plugin,
  suggest re-running /speckit-tasks, and ask whether to continue anyway (every task then
  runs without a skill).
- Show the waves summary.

## The loop (repeat until `next` prints DONE)

1. `{{SW}} next <FEATURE_DIR>/tasks.md`
   It prints the current wave: a table and one brief per skill group. Each brief already
   tells the worker which SKILL.md to read first.

2. Launch one sub-agent per brief, ALL in the same turn so they run in parallel, passing each
   brief verbatim (Claude Code: one Agent tool call per brief in a single message). Do not
   summarise, merge, reorder or add tasks.
   If sub-agents are not available, run the briefs yourself one after another; at the start
   of each, read its SKILL.md with your file-reading tool. Do not rely on the skill
   triggering by itself.

3. Read every report (DONE / FAILED / TOUCHED / NOTES) before doing anything else.
   A path in TOUCHED of two workers, or a path from a worker's "Must NOT edit" list, is a
   possible collision: review that file's diff with the user.

4. Record progress, only for reported DONE ids:
   `{{SW}} mark <FEATURE_DIR>/tasks.md T001 T002 ...`

5. Run the project's fast checks (tests, lint) if obvious from plan.md / Makefile /
   package.json / pyproject.toml.

6. If any task FAILED or checks fail: STOP before the next wave. Report per group what
   succeeded, what failed and why, and what is blocked. Offer: retry the group (run `next`
   again, failed tasks are still pending), fix by hand then `mark`, or skip (only if the user
   says so). Otherwise go to step 1.

## When `next` prints DONE

Run `{{SW}} plan <FEATURE_DIR>/tasks.md --write --markdown` once more, run the full test
suite, then do the completion validation from the implement command. Report: waves run,
tasks done/skipped, skills used, files touched, test results, and NOTES that need a decision.

Re-running /speckit-implement is safe: `next` resumes from the checkboxes.
