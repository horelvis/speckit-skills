#!/usr/bin/env python3
"""Claude Code hook: add skill-binding instructions to Spec Kit commands.

Fires on UserPromptExpansion (user types /speckit-plan, /speckit-tasks, /speckit-implement)
and on PreToolUse for the Skill tool (the model invokes them, e.g. via handoffs).
Does nothing outside Spec Kit projects (no .specify/ directory) or when disabled with
SPECKIT_SKILLS_DISABLE=1 or a `.specify/speckit-skills.off` file in the project.
Never blocks: any problem results in a silent exit 0.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = {"speckit-plan": "plan", "speckit-tasks": "tasks", "speckit-implement": "implement"}


def command_of(event: dict) -> str | None:
    if event.get("hook_event_name") == "UserPromptExpansion":
        name = event.get("command_name") or ""
    elif event.get("hook_event_name") == "PreToolUse" and event.get("tool_name") == "Skill":
        name = (event.get("tool_input") or {}).get("skill") or ""
    else:
        return None
    name = name.lstrip("/").split(":")[-1].replace(".", "-").lower()
    return COMMANDS.get(name)


def project_root(event: dict) -> Path | None:
    for base in (os.environ.get("CLAUDE_PROJECT_DIR"), event.get("cwd"), os.getcwd()):
        if not base:
            continue
        p = Path(base).resolve()
        for d in (p, *p.parents):
            if (d / ".specify").is_dir():
                return d
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = command_of(event)
    if not cmd or os.environ.get("SPECKIT_SKILLS_DISABLE") == "1":
        return 0
    root = project_root(event)
    if root is None or (root / ".specify" / "speckit-skills.off").exists():
        return 0
    try:
        text = (ROOT / "instructions" / f"{cmd}.md").read_text(encoding="utf-8")
    except OSError:
        return 0
    sw = f'python3 "{ROOT / "scripts" / "skill_waves.py"}" --project "{root}"'
    text = text.replace("{{SW}}", sw)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": event["hook_event_name"],
        "additionalContext": text,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
