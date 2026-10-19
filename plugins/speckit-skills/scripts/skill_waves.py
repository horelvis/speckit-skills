#!/usr/bin/env python3
"""skill_waves: bind Spec Kit tasks to agent skills and run them in waves grouped by skill.

Subcommands
  discover                     Skills available to the project (JSON).
  plan  TASKS_MD [--write]     Validate tasks.md and compute waves. --write refreshes the
                               "Execution Waves" section inside tasks.md. JSON by default,
                               --markdown for a human table.
  next  TASKS_MD               Print the next wave to run: one brief per skill group,
                               ready to hand to a sub-agent. Prints DONE when nothing is left.
  mark  TASKS_MD ID... | --report FILE
                               Tick tasks as done ([X]). --report reads a worker reply and
                               ticks the ids on its "DONE:" line.

Task annotations (same syntax as spec-kit-schedule, so tasks.md works with both):
  - [ ] T012 [P] [US1] Create POST /users in src/api/users.py (skill: fastapi-endpoints) (depends on T010, T011)
  (skill: none) and (depends on none) are explicit "nothing".

Rules
  * ## headings (phases) are barriers.
  * Inside a phase: wave(t) = 1 + max(wave(dep)). Without (depends on ...), core semantics:
    [P] waits for prior non-[P] tasks of the phase, non-[P] waits for every prior task.
  * Tasks of different skill groups in the same wave never share a file: the later one is
    moved to the next wave (with its dependents).
  * Each wave = groups by skill; groups of one wave are independent (parallel-safe).

Standard library only. Exit codes: 0 ok, 1 validation error, 2 usage/IO error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

TASK_RE = re.compile(r"^\s*-\s+\[(?P<check>[ xX]?)\]\s+(?P<id>T\d+)\b(?P<tags>(?:\s+\[(?:P|US\d+)\])*)\s+(?P<desc>.+?)\s*$")
STORY_RE = re.compile(r"\[(US\d+)\]")
DEPENDS_RE = re.compile(r"\(\s*depends\s+on\s+(?P<v>[^)]+)\)", re.I)
SKILL_RE = re.compile(r"\(\s*skill:\s*(?P<v>[^)\s]+)\s*\)", re.I)
SCHEDULE_SKILL_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
ID_RE = re.compile(r"\bT\d+\b")
PATH_RE = re.compile(r"(?<![\w/])((?:[\w.-]+/)+[\w.-]+|[\w-]+\.[A-Za-z]\w{0,7})(?![\w/])")
START, END = "<!-- skill-waves:start -->", "<!-- skill-waves:end -->"
NONE = "none"


# ------------------------------------------------------------------ discovery

def _frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict = {}
    key = None
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            out[key] = "" if val in (">", "|", ">-", "|-") else val.strip("'\"")
        elif key and line[:1] in (" ", "\t"):
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def skill_roots(project: Path) -> list[Path]:
    home = Path.home()
    roots = [project / ".claude" / "skills", project / ".github" / "skills", project / ".agents" / "skills",
             home / ".claude" / "skills", home / ".agents" / "skills"]
    plugins = home / ".claude" / "plugins"
    if plugins.is_dir():
        roots += sorted(p for p in plugins.glob("**/skills") if p.is_dir())
    roots += [Path(p).expanduser() for p in os.environ.get("SKILL_WAVES_DIRS", "").split(os.pathsep) if p]
    return roots


def discover(project: Path) -> dict[str, dict]:
    skills: dict[str, dict] = {}
    for root in skill_roots(project):
        if not root.is_dir():
            continue
        for md in sorted(root.glob("*/SKILL.md")):
            try:
                fm = _frontmatter(md.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            name = fm.get("name") or md.parent.name
            if name.startswith("speckit"):
                continue  # Spec Kit's own commands, not domain skills
            skills.setdefault(name, {"name": name, "description": fm.get("description", ""), "path": str(md)})
    return skills


# ------------------------------------------------------------------ parsing

def parse(text: str) -> list[dict]:
    """Return phases [{name, tasks}]; ignores the generated waves section."""
    phases: list[dict] = []
    cur = {"name": "(preamble)", "tasks": []}
    skip = False
    for n, line in enumerate(text.splitlines(), 1):
        if START in line:
            skip = True
            continue
        if END in line:
            skip = False
            continue
        if skip:
            continue
        if line.startswith("## "):
            if cur["tasks"]:
                phases.append(cur)
            cur = {"name": line[3:].strip(), "tasks": []}
            continue
        m = TASK_RE.match(line)
        if not m:
            continue
        desc = m.group("desc")
        skills = deps = None
        dm = DEPENDS_RE.search(desc)
        if dm:
            deps = ID_RE.findall(dm.group("v"))
            desc = desc[:dm.start()] + desc[dm.end():]
        sm = SKILL_RE.search(desc)
        if sm:
            v = sm.group("v").strip()
            skills = [] if v.lower() in (NONE, "-") else [v]
            desc = desc[:sm.start()] + desc[sm.end():]
        desc = re.sub(r"\s{2,}", " ", desc).strip()
        tags = m.group("tags")
        st = STORY_RE.search(tags)
        cur["tasks"].append({
            "id": m.group("id"), "done": m.group("check").lower() == "x", "line": n,
            "parallel": "[P]" in tags, "story": st.group(1) if st else None,
            "skills": skills, "deps": deps, "desc": desc,
            "files": sorted({p.rstrip(".,;:)") for p in PATH_RE.findall(desc)}),
        })
    if cur["tasks"]:
        phases.append(cur)
    return phases


# ------------------------------------------------------------------ planning

def gkey(t: dict) -> str:
    return t["skills"][0] if t["skills"] else NONE


def plan(text: str, available: dict[str, dict]) -> dict:
    phases = parse(text)
    tasks = [t for ph in phases for t in ph["tasks"]]
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    for t in tasks:
        if t["id"] in seen_ids:
            errors.append(f"{t['id']}: duplicated task id")
        seen_ids.add(t["id"])
        if t["skills"] is None:
            warnings.append(f"{t['id']}: no (skill: ...) annotation, treated as (skill: none)")
            t["skills"] = []
        for s in t["skills"]:
            if s not in available:
                errors.append(f"{t['id']}: skill '{s}' is not installed")
            elif not SCHEDULE_SKILL_NAME.match(s):
                warnings.append(f"{t['id']}: skill name '{s}' is not spec-kit-schedule compatible ([a-z][a-z0-9_-]*)")
    phase_of = {t["id"]: i for i, ph in enumerate(phases) for t in ph["tasks"]}

    out = []
    for pi, ph in enumerate(phases):
        local = {t["id"]: t for t in ph["tasks"]}
        order = [t["id"] for t in ph["tasks"]]
        deps: dict[str, list[str]] = {}
        for i, t in enumerate(ph["tasks"]):
            if t["deps"] is not None:
                d = []
                for x in t["deps"]:
                    if x not in phase_of:
                        errors.append(f"{t['id']}: depends on unknown task {x}")
                    elif phase_of[x] > pi:
                        errors.append(f"{t['id']}: depends on {x}, which is in a later phase")
                    elif x in local:
                        d.append(x)
                deps[t["id"]] = d
            else:
                prior = ph["tasks"][:i]
                deps[t["id"]] = [p["id"] for p in prior if not p["parallel"]] if t["parallel"] else [p["id"] for p in prior]

        floor = {tid: 1 for tid in order}
        cycles: set[str] = set()

        def compute() -> dict[str, int]:
            w: dict[str, int] = {}
            visiting: set[str] = set()

            def lvl(tid: str) -> int:
                if tid in w:
                    return w[tid]
                if tid in visiting:
                    if tid not in cycles:
                        cycles.add(tid)
                        errors.append(f"{tid}: dependency cycle")
                    return 1
                visiting.add(tid)
                v = max(floor[tid], 1 + max((lvl(d) for d in deps[tid]), default=0))
                visiting.discard(tid)
                w[tid] = v
                return v

            for tid in order:
                lvl(tid)
            return w

        wave = compute()
        for _ in range(len(order) ** 2 + 1):
            conflict = None
            for wn in sorted(set(wave.values())):
                owner: dict[str, tuple[str, str]] = {}
                for tid in (x for x in order if wave[x] == wn):
                    g = gkey(local[tid])
                    for f in local[tid]["files"]:
                        if f in owner and owner[f][1] != g:
                            conflict = (tid, f, owner[f][0], wn)
                            break
                        owner.setdefault(f, (tid, g))
                    if conflict:
                        break
                if conflict:
                    break
            if not conflict:
                break
            tid, f, other, wn = conflict
            warnings.append(f"{tid}: shares {f} with {other} (other skill group); moved after wave {wn}")
            floor[tid] = wn + 1
            wave = compute()

        waves = []
        for wn in sorted(set(wave.values())):
            groups: dict[str, list[dict]] = {}
            for tid in order:
                if wave[tid] == wn:
                    groups.setdefault(gkey(local[tid]), []).append(local[tid])
            waves.append({"wave": wn, "groups": [{
                "skill": k,
                "skill_path": available[k]["path"] if k in available else None,
                "tasks": [{"id": t["id"], "done": t["done"], "story": t["story"], "desc": t["desc"], "files": t["files"]} for t in ts],
                "pending": sum(not t["done"] for t in ts),
            } for k, ts in sorted(groups.items(), key=lambda kv: (kv[0] == NONE, kv[0]))]})
        out.append({"phase": ph["name"], "waves": waves})

    groups_all = [g for ph in out for w in ph["waves"] for g in w["groups"]]
    return {
        "phases": out,
        "stats": {"tasks": len(tasks), "pending": sum(not t["done"] for t in tasks),
                  "waves": sum(len(ph["waves"]) for ph in out), "groups": len(groups_all),
                  "single_task_groups": sum(len(g["tasks"]) == 1 for g in groups_all),
                  "skills_used": sorted({s for t in tasks for s in t["skills"]})},
        "errors": errors, "warnings": warnings,
    }


# ------------------------------------------------------------------ rendering

def render_section(p: dict) -> str:
    L = [START, "", "## Execution Waves", "",
         "_Generated by speckit-skills. Do not edit: regenerate with `skill_waves.py plan --write`._",
         "_Phases are barriers; waves run in order; skill groups of one wave run in parallel._", ""]
    for ph in p["phases"]:
        L += [f"### {ph['phase']}", "", "| Wave | Skill | Tasks |", "|------|-------|-------|"]
        for w in ph["waves"]:
            for g in w["groups"]:
                ids = ", ".join(f"~~{t['id']}~~" if t["done"] else t["id"] for t in g["tasks"])
                L.append(f"| {w['wave']} | `{g['skill']}` | {ids} |")
        L.append("")
    s = p["stats"]
    L += [f"{s['tasks']} tasks ({s['pending']} pending) · {s['waves']} waves · {s['groups']} groups "
          f"({s['single_task_groups']} single-task) · skills: {', '.join(s['skills_used']) or 'none'}", "", END]
    return "\n".join(L)


def render_next(p: dict, feature_dir: Path) -> str:
    for ph in p["phases"]:
        for w in ph["waves"]:
            groups = [g for g in w["groups"] if g["pending"]]
            if not groups:
                continue
            total_w = len(ph["waves"])
            L = [f"# {ph['phase']} · wave {w['wave']} of {total_w} · {len(groups)} group(s)", "",
                 "| Group | Skill | Tasks |", "|-------|-------|-------|"]
            for i, g in enumerate(groups, 1):
                L.append(f"| {i} | `{g['skill']}` | {', '.join(t['id'] for t in g['tasks'] if not t['done'])} |")
            L += ["", "Launch one sub-agent per group, all in the same turn, each with its brief VERBATIM.", ""]
            for i, g in enumerate(groups, 1):
                mine = {f for t in g["tasks"] for f in t["files"]}
                others = sorted({f for o in groups if o is not g for t in o["tasks"] for f in t["files"]} - mine)
                L += ["---", "", f"## Brief {i}: skill `{g['skill']}`", "", "```text"]
                L.append(f"You are implementing part of the feature in {feature_dir}.")
                L.append("")
                if g["skill_path"]:
                    L.append(f"STEP 0 (mandatory): read {g['skill_path']} completely and apply it to every task below.")
                else:
                    L.append("No skill applies to these tasks: follow the project's existing conventions.")
                L += ["", "Context (read what you need):",
                      f"- {feature_dir}/plan.md and {feature_dir}/spec.md",
                      f"- {feature_dir}/data-model.md, contracts/, research.md (if present)",
                      "- .specify/memory/constitution.md (if present)", "",
                      "Tasks, in this order:"]
                for t in g["tasks"]:
                    if not t["done"]:
                        L.append(f"- {t['id']} {t['desc']}")
                if others:
                    L += ["", "Must NOT edit (owned by other workers in this wave): " + ", ".join(others)]
                L += ["", "Rules: do only these tasks; do not edit tasks.md; after each task run the narrowest",
                      "relevant check (test/lint/typecheck) if one exists.", "",
                      "End your reply with exactly:",
                      "DONE: <ids>", "FAILED: <id> <reason>   (omit if none)",
                      "TOUCHED: <paths>", "NOTES: <anything the orchestrator must know>", "```", ""]
            return "\n".join(L)
    return "DONE"


# ------------------------------------------------------------------ mark

def mark(path: Path, ids: list[str]) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    want, hit = set(ids), set()
    for i, line in enumerate(lines):
        m = TASK_RE.match(line.rstrip("\n"))
        if m and m.group("id") in want:
            lines[i] = re.sub(r"\[[ xX]?\]", "[X]", line, count=1)
            hit.add(m.group("id"))
    path.write_text("".join(lines), encoding="utf-8")
    return sorted(want - hit)


def ids_from_report(text: str) -> list[str]:
    for line in text.splitlines():
        if line.strip().upper().startswith("DONE:"):
            return ID_RE.findall(line)
    return []


# ------------------------------------------------------------------ cli

def write_section(path: Path, section: str) -> None:
    text = path.read_text(encoding="utf-8")
    if START in text and END in text:
        text = text[:text.index(START)] + section + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + "\n\n---\n\n" + section + "\n"
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skill_waves")
    ap.add_argument("--project", default=".", help="project root (default: cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover")
    pp = sub.add_parser("plan")
    pp.add_argument("tasks_md")
    pp.add_argument("--write", action="store_true")
    pp.add_argument("--markdown", action="store_true")
    np_ = sub.add_parser("next")
    np_.add_argument("tasks_md")
    mp = sub.add_parser("mark")
    mp.add_argument("tasks_md")
    mp.add_argument("ids", nargs="*")
    mp.add_argument("--report")
    a = ap.parse_args(argv)

    project = Path(a.project).resolve()
    if a.cmd == "discover":
        print(json.dumps({"skills": list(discover(project).values())}, indent=2, ensure_ascii=False))
        return 0

    tasks_md = Path(a.tasks_md)
    if not tasks_md.is_file():
        print(f"tasks file not found: {tasks_md}", file=sys.stderr)
        return 2

    if a.cmd == "mark":
        ids = list(a.ids)
        if a.report:
            ids += ids_from_report(Path(a.report).read_text(encoding="utf-8"))
        if not ids:
            print("nothing to mark", file=sys.stderr)
            return 2
        missing = mark(tasks_md, ids)
        print(f"marked: {' '.join(sorted(set(ids) - set(missing)))}")
        if missing:
            print(f"not found: {' '.join(missing)}", file=sys.stderr)
            return 1
        return 0

    result = plan(tasks_md.read_text(encoding="utf-8"), discover(project))
    if a.cmd == "next":
        if result["errors"]:
            print("Plan is invalid, fix tasks.md first:\n" + "\n".join(f"- {e}" for e in result["errors"]), file=sys.stderr)
            return 1
        print(render_next(result, tasks_md.resolve().parent))
        return 0

    if a.write and not result["errors"]:
        write_section(tasks_md, render_section(result))
    if a.markdown:
        print(render_section(result))
        for e in result["errors"]:
            print(f"ERROR {e}", file=sys.stderr)
        for w in result["warnings"]:
            print(f"WARN  {w}", file=sys.stderr)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
