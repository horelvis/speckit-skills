# speckit-skills: extra rules for this /speckit-tasks run

The speckit-skills plugin is active in this project. Everything in the tasks command still
applies (phases by user story, checklist format, MVP first). In addition, every task carries
two trailing annotations, in this syntax (shared with spec-kit-schedule):

```text
- [ ] T012 [P] [US1] Create POST /users in src/api/users.py (skill: fastapi-endpoints) (depends on T010, T011)
- [ ] T001 Create project structure per implementation plan (skill: none) (depends on none)
```

## (skill: name), required on every task

- Take it from the "Skills Map" in plan.md: find the area of the task and copy its skill.
- If plan.md has no Skills Map, run `{{SW}} discover` and map from its output.
- `(skill: none)` when nothing applies. Never a name that is not installed.
- One skill per task. If a task needs two (an endpoint and its test), split it.

## (depends on IDs), required on every task

- Only tasks of the SAME phase that must finish first. `(depends on none)` if none.
- Earlier phases are implicit (phases are barriers). Never depend on a later phase.
- Be precise, not conservative: a missing dependency breaks the build, an unnecessary one
  serializes work and prevents grouping tasks by skill.
- TDD (when tests are requested): the implementation task depends on its test task.
- Keep exact file paths in descriptions; they are used to detect file conflicts.

## After writing tasks.md (before hooks and completion report)

1. Run: `{{SW}} plan <FEATURE_DIR>/tasks.md --write --markdown`
2. On errors (skill not installed, cycle, unknown or later-phase dependency): fix those task
   lines and run it again until it exits 0. Never edit the "Execution Waves" section by hand.
3. Warnings:
   - "no (skill: ...)": add the annotation.
   - "shares <file> ...": acceptable; if frequent, the task split is wrong.
   - if most groups are single-task, dependencies are probably too conservative; review once.
4. Add to the completion report: waves per phase, groups, skills used, remaining warnings.
