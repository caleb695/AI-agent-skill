#!/usr/bin/env python3
"""Claude Code Stop hook backed by the Relentless executable state gates.

The hook prints a top-level Stop decision on stdout and always exits zero for a
valid decision. A physical user interrupt does not invoke Stop hooks in Claude
Code; an explicit conversational stop can be recorded with `relentless.py stop`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from relentless import ACTIVE, completion_blockers, default_state_path, load_state


def decision(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


def controller_command(path: Path, session_id: Optional[str] = None) -> str:
    controller = Path(__file__).resolve().with_name("relentless.py")
    if session_id:
        return f'python3 "{controller}" --session "{session_id}"'
    return f'python3 "{controller}" --state "{path}"'


def main(payload: Optional[Dict[str, Any]] = None) -> int:
    if payload is None:
        try:
            payload = json.load(sys.stdin)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return 0
    if not isinstance(payload, dict):
        return 0
    if payload.get("hook_event_name", "Stop") != "Stop":
        return 0

    session_id = payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID")
    cwd = payload.get("cwd") or os.getcwd()
    path = default_state_path(cwd=cwd, session_id=session_id)
    base = controller_command(path)

    if not path.exists():
        initializer = controller_command(path, session_id) if session_id else base
        decision(
            "Relentless was invoked but has no durable task state. Use a tool now to run "
            f"`{initializer} init --objective '<the actual user objective>'`, then register every "
            "requirement with requirement-add. Do not bypass initialization or claim completion."
        )
        return 0

    try:
        state = load_state(path)
    except Exception as exc:  # The hook must return valid JSON even for damaged state.
        decision(
            f"Relentless state at {path} could not be loaded ({exc}). Inspect and repair the state "
            "without fabricating evidence, or record an explicit user stop. Do not treat a damaged "
            "state file as task completion."
        )
        return 0

    # An explicitly shared --state file must not block an unrelated session.
    if state.get("session_id") and session_id and state["session_id"] != session_id:
        return 0
    if state["status"] != ACTIVE:
        return 0

    blockers = completion_blockers(state)
    continuation = (
        "This Stop hook has already continued the turn; make a tool call now rather than replying "
        "with another status message. "
        if payload.get("stop_hook_active")
        else ""
    )
    if not blockers:
        decision(
            continuation
            + "All Relentless evidence gates pass, but completion has not been recorded. Run "
            f"`{base} complete --summary '<evidence-backed result summary>'`, then report the result. "
            "Do not bypass the executable completion gate."
        )
        return 0

    shown = "; ".join(blockers[:6])
    remaining = len(blockers) - 6
    if remaining > 0:
        shown += f"; and {remaining} more"
    decision(
        continuation
        + f"Relentless task remains active: {state['objective']}. Completion is blocked: {shown}. "
        f"Run `{base} status`, apply prior lessons, and take a concrete tool-backed action toward "
        "the unresolved gates. Record each attempt and its lesson. If a meta-review is required, "
        "use the review command before another attempt. Only a successful complete command or an "
        "explicit user stop may end this task; never fabricate evidence or relax requirements."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
