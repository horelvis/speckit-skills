import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "speckit-skills"
sys.path.insert(0, str(PLUGIN / "scripts"))
import skill_waves as sw  # noqa: E402

SKILLS = {n: {"name": n, "description": "", "path": f"/s/{n}/SKILL.md"} for n in ("api", "db", "tests")}


def waves(r, phase=0):
    return [(w["wave"], g["skill"], [t["id"] for t in g["tasks"]]) for w in r["phases"][phase]["waves"] for g in w["groups"]]


class Planning(unittest.TestCase):
    def test_groups_by_skill_inside_wave(self):
        md = """## Phase 3: US1
- [ ] T001 [P] [US1] test a in tests/a.py (skill: tests) (depends on none)
- [ ] T002 [P] [US1] test b in tests/b.py (skill: tests) (depends on none)
- [ ] T003 [US1] model in src/m.py (skill: db) (depends on none)
- [ ] T004 [US1] endpoint in src/e.py (depends on T003, T001) (skill: api)
"""
        r = sw.plan(md, SKILLS)
        self.assertEqual(r["errors"], [])
        self.assertEqual(waves(r), [(1, "db", ["T003"]), (1, "tests", ["T001", "T002"]), (2, "api", ["T004"])])
        self.assertEqual(r["phases"][0]["waves"][1]["groups"][0]["tasks"][0]["desc"], "endpoint in src/e.py")

    def test_phase_barrier(self):
        md = "## Phase 1\n- [ ] T001 a in src/a.py (skill: db) (depends on none)\n## Phase 2\n- [ ] T002 b in src/b.py (skill: api) (depends on T001)\n"
        r = sw.plan(md, SKILLS)
        self.assertEqual(r["errors"], [])
        self.assertEqual(waves(r, 1), [(1, "api", ["T002"])])

    def test_core_semantics_without_depends(self):
        md = """## Phase 1
- [ ] T001 a in src/a.py (skill: db)
- [ ] T002 [P] b in src/b.py (skill: db)
- [ ] T003 [P] c in src/c.py (skill: api)
- [ ] T004 d in src/d.py (skill: api)
"""
        self.assertEqual(waves(sw.plan(md, SKILLS)), [(1, "db", ["T001"]), (2, "api", ["T003"]), (2, "db", ["T002"]), (3, "api", ["T004"])])

    def test_file_conflict_moves_task_and_dependents(self):
        md = """## Phase 1
- [ ] T001 router in src/app.py (skill: api) (depends on none)
- [ ] T002 engine in src/app.py (skill: db) (depends on none)
- [ ] T003 seed in src/seed.py (skill: db) (depends on T002)
"""
        r = sw.plan(md, SKILLS)
        self.assertEqual(waves(r), [(1, "api", ["T001"]), (2, "db", ["T002"]), (3, "db", ["T003"])])
        self.assertTrue(any("src/app.py" in w for w in r["warnings"]))

    def test_same_group_may_share_files(self):
        md = "## P\n- [ ] T001 a in src/m.py (skill: db) (depends on none)\n- [ ] T002 b in src/m.py (skill: db) (depends on none)\n"
        self.assertEqual(waves(sw.plan(md, SKILLS)), [(1, "db", ["T001", "T002"])])

    def test_errors(self):
        md = """## Phase 1
- [ ] T001 a (skill: nope) (depends on T002)
- [ ] T002 b (skill: db) (depends on T001)
- [ ] T003 c (skill: db) (depends on T005)
## Phase 2
- [ ] T005 e (skill: db) (depends on none)
- [ ] T006 f (skill: db) (depends on T099)
"""
        errs = " | ".join(sw.plan(md, SKILLS)["errors"])
        for needle in ("'nope' is not installed", "dependency cycle", "later phase", "unknown task T099"):
            self.assertIn(needle, errs)

    def test_missing_skill_is_warning_and_none(self):
        r = sw.plan("## P\n- [ ] T001 a (depends on none)\n", SKILLS)
        self.assertEqual(r["errors"], [])
        self.assertEqual(waves(r), [(1, "none", ["T001"])])
        self.assertTrue(r["warnings"])

    def test_generated_section_ignored(self):
        md = "## P\n- [ ] T001 a in src/a.py (skill: db) (depends on none)\n"
        md2 = md + "\n" + sw.render_section(sw.plan(md, SKILLS)) + "\n"
        self.assertEqual(sw.plan(md2, SKILLS)["stats"]["tasks"], 1)


class NextAndMark(unittest.TestCase):
    MD = """## Phase 1
- [X] T001 setup (skill: none) (depends on none)
## Phase 2
- [ ] T002 [P] test in tests/t.py (skill: tests) (depends on none)
- [ ] T003 model in src/m.py (skill: db) (depends on none)
- [ ] T004 api in src/a.py (skill: api) (depends on T003)
"""

    def test_next_emits_current_wave_with_skill_paths(self):
        out = sw.render_next(sw.plan(self.MD, SKILLS), Path("/f"))
        self.assertIn("Phase 2 · wave 1 of 2 · 2 group(s)", out)
        self.assertIn("read /s/db/SKILL.md", out)
        self.assertIn("read /s/tests/SKILL.md", out)
        self.assertNotIn("T004", out)
        self.assertIn("Must NOT edit", out)

    def test_next_resumes_and_finishes(self):
        md = self.MD.replace("- [ ] T002", "- [X] T002").replace("- [ ] T003", "- [X] T003")
        out = sw.render_next(sw.plan(md, SKILLS), Path("/f"))
        self.assertIn("wave 2 of 2", out)
        self.assertIn("T004 api in src/a.py", out)
        self.assertEqual(sw.render_next(sw.plan(md.replace("- [ ] T004", "- [X] T004"), SKILLS), Path("/f")), "DONE")

    def test_failed_task_is_reemitted(self):
        md = self.MD.replace("- [ ] T002", "- [X] T002")  # T003 failed, still pending
        out = sw.render_next(sw.plan(md, SKILLS), Path("/f"))
        self.assertIn("wave 1 of 2 · 1 group(s)", out)
        self.assertIn("T003", out)

    def test_mark_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tasks.md"
            p.write_text(self.MD)
            self.assertEqual(sw.mark(p, ["T002", "T999"]), ["T999"])
            self.assertIn("- [X] T002", p.read_text())
            ids = sw.ids_from_report("blah\nDONE: T003 T004\nFAILED: none\n")
            self.assertEqual(ids, ["T003", "T004"])


class Hook(unittest.TestCase):
    def run_hook(self, event, cwd):
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        r = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "inject.py")], input=json.dumps(event),
                           capture_output=True, text=True, cwd=cwd, env=env)
        self.assertEqual(r.returncode, 0)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_injects_only_in_spec_kit_projects(self):
        with tempfile.TemporaryDirectory() as d:
            ev = {"hook_event_name": "UserPromptExpansion", "command_name": "speckit-tasks", "cwd": d}
            self.assertIsNone(self.run_hook(ev, d))
            (Path(d) / ".specify").mkdir()
            out = self.run_hook(ev, d)
            ctx = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("(skill: name)", ctx)
            self.assertIn("skill_waves.py", ctx)
            self.assertNotIn("{{SW}}", ctx)

    def test_model_invoked_skill_and_other_commands(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".specify").mkdir()
            ev = {"hook_event_name": "PreToolUse", "tool_name": "Skill", "tool_input": {"skill": "speckit-implement"}, "cwd": d}
            self.assertEqual(self.run_hook(ev, d)["hookSpecificOutput"]["hookEventName"], "PreToolUse")
            ev["tool_input"]["skill"] = "speckit-specify"
            self.assertIsNone(self.run_hook(ev, d))
            (Path(d) / ".specify" / "speckit-skills.off").touch()
            ev["tool_input"]["skill"] = "speckit-plan"
            self.assertIsNone(self.run_hook(ev, d))


if __name__ == "__main__":
    unittest.main()
