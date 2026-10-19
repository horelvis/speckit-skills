# speckit-skills: extra step for this /speckit-plan run

The speckit-skills plugin is active in this project. Do everything the plan command says, and
before the post-execution hooks and the completion report, add this step.

## Skills Map

1. Run: `{{SW}} discover`
   It lists the agent skills installed for this project (name, description, path).
   Spec Kit's own `speckit-*` skills are already excluded.

2. From plan.md (Technical Context, Project Structure), data-model.md and contracts/, list the
   work areas of THIS feature: persistence, API, UI, tests, infra, docs... Coarse areas,
   typically 4 to 10. Not tasks.

3. For each area choose at most one skill whose description clearly covers that kind of work:
   - only names returned by `discover`, copied exactly;
   - if two fit, choose the more specific and mention the other;
   - if none fits, write `none`. A wrong skill is worse than no skill;
   - read a SKILL.md only when its description is ambiguous.

4. Append this section to plan.md (replace it if it already exists):

   ```markdown
   ## Skills Map

   | Area | Paths / layer | Skill | Why |
   |------|---------------|-------|-----|
   | Data model | src/models/ | sqlalchemy-models | ORM models and migrations |
   | Docs | docs/ | none | no documentation skill installed |

   **Gaps**: areas with recurring work and no skill (candidates for a new skill).
   ```

5. Include the Skills Map and the gaps in the completion report.
