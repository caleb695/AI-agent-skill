#!/usr/bin/env python3
"""Durable state and executable completion gates for the Relentless skill.

Uses only the Python standard library. Every mutation is persisted atomically and
append-only audit events are written beside the state file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_VERSION = 1
ACTIVE = "active"
COMPLETED = "completed"
STOPPED = "stopped"
IN_PROGRESS = "in_progress"
FINISHED = "finished"
INTERRUPTED = "interrupted"


class CommandError(Exception):
    """A user-actionable command failure."""

    def __init__(self, message: str, code: int = 2, details: Optional[Any] = None):
        super().__init__(message)
        self.code = code
        self.details = details


def now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp() -> str:
    return now().isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def required_text(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise CommandError(f"{field} must not be empty")
    return cleaned


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def default_state_path(
    cwd: Optional[os.PathLike[str] | str] = None,
    session_id: Optional[str] = None,
) -> Path:
    """Resolve an out-of-tree durable state path for a session or workspace."""

    working_dir = Path(cwd or os.getcwd()).expanduser().resolve()
    override = os.environ.get("RELENTLESS_STATE")
    if override:
        path = Path(override).expanduser()
        return path if path.is_absolute() else working_dir / path

    state_home = os.environ.get("RELENTLESS_STATE_HOME")
    if state_home:
        root = Path(state_home).expanduser()
    else:
        xdg_home = os.environ.get("XDG_STATE_HOME")
        root = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".local" / "state"
        root = root / "relentless"

    session_id = session_id or os.environ.get("CLAUDE_SESSION_ID")
    if session_id:
        kind, identity = "session", session_id
    else:
        kind, identity = "workspace", str(working_dir)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return root / f"{kind}-{digest}.json"


def event_path(path: Path) -> Path:
    return Path(str(path) + ".events.jsonl")


def load_state(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError:
        raise CommandError(f"No Relentless state exists at {path}; run init first", code=4)
    except json.JSONDecodeError as exc:
        raise CommandError(f"State file {path} is not valid JSON: {exc}", code=4)

    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        raise CommandError(f"State file {path} has an unsupported or missing version", code=4)
    if state.get("status") not in {ACTIVE, COMPLETED, STOPPED}:
        raise CommandError(f"State file {path} has an invalid status", code=4)
    for field in ("requirements", "attempts", "lessons", "reviews"):
        if not isinstance(state.get(field), list):
            raise CommandError(f"State file {path} is missing the {field} list", code=4)
    return state


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            os.chmod(temporary, 0o600)
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def append_event(path: Path, event_type: str, details: Optional[Dict[str, Any]] = None) -> None:
    event = {"at": timestamp(), "type": event_type, "details": details or {}}
    audit_path = event_path(path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(audit_path, 0o600)


def save_state(
    path: Path,
    state: Dict[str, Any],
    event_type: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    state["updated_at"] = timestamp()
    atomic_write_json(path, state)
    append_event(path, event_type, details)


def archive_inactive_state(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    state = load_state(path)
    if state["status"] == ACTIVE:
        raise CommandError(
            f"An active task already exists at {path}; resume it or use a different --state",
            code=3,
        )
    suffix = now().strftime("%Y%m%dT%H%M%S%fZ")
    archive = path.with_name(f"{path.stem}.{suffix}{path.suffix}")
    path.replace(archive)
    old_events = event_path(path)
    if old_events.exists():
        old_events.replace(event_path(archive))
    return str(archive)


def require_active(state: Dict[str, Any]) -> None:
    if state["status"] != ACTIVE:
        raise CommandError(f"Task is {state['status']}; only an active task can be changed", code=3)


def requirement(state: Dict[str, Any], requirement_id: str) -> Dict[str, Any]:
    for item in state["requirements"]:
        if item["id"] == requirement_id:
            return item
    raise CommandError(f"Unknown requirement {requirement_id}", code=4)


def active_attempt(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return next((item for item in state["attempts"] if item["status"] == IN_PROGRESS), None)


def review_reasons(state: Dict[str, Any]) -> List[str]:
    """Return deterministic triggers for a mandatory strategy meta-review."""

    last_review = state.get("last_review_attempt_id", 0)
    recent = [
        item
        for item in state["attempts"]
        if item["id"] > last_review and item["status"] == FINISHED
    ]
    failed = [item for item in recent if item.get("outcome") == "failed"]
    reasons: List[str] = []

    strategy_counts = Counter(normalized(item["strategy"]) for item in failed)
    repeated = [strategy for strategy, count in strategy_counts.items() if count >= 2]
    if repeated:
        reasons.append(
            "two failures in strategy family since the last review: " + ", ".join(sorted(repeated))
        )
    if len(failed) >= 3:
        reasons.append("three failed attempts since the last review")
    if len(recent) >= 5:
        first_attempt = min(parse_timestamp(item["started_at"]) for item in recent)
        made_progress = any(
            item.get("verified_at") and parse_timestamp(item["verified_at"]) >= first_attempt
            for item in state["requirements"]
        )
        if not made_progress:
            reasons.append("five attempts since the last review without a newly verified requirement")
    return reasons


def completion_blockers(state: Dict[str, Any], at: Optional[datetime] = None) -> List[str]:
    """Compute all conditions that currently prohibit a completion claim."""

    if state["status"] != ACTIVE:
        return []
    blockers: List[str] = []
    requirements = state["requirements"]
    if not requirements:
        blockers.append("no requirements are registered")
    for item in requirements:
        if item["status"] != "verified":
            blockers.append(f"{item['id']} is unverified: {item['description']}")
            continue
        if not item.get("evidence"):
            blockers.append(f"{item['id']} has no completion evidence")
        if item.get("current"):
            if not item.get("sources"):
                blockers.append(f"{item['id']} is current-sensitive but has no source")
            if not item.get("freshness_note"):
                blockers.append(f"{item['id']} is current-sensitive but has no freshness note")
            verified_at = item.get("verified_at")
            if not verified_at:
                blockers.append(f"{item['id']} has no verification timestamp")
            else:
                age = (at or now()) - parse_timestamp(verified_at)
                if age > timedelta(minutes=item["max_age_minutes"]):
                    blockers.append(
                        f"{item['id']} current-source verification is stale "
                        f"(older than {item['max_age_minutes']} minutes)"
                    )
    attempt = active_attempt(state)
    if attempt:
        blockers.append(f"attempt {attempt['id']} is still in progress")
    blockers.extend("meta-review required: " + reason for reason in review_reasons(state))
    return blockers


def output_tail(value: Any, limit: int = 4000) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return (value or "")[-limit:]


def run_completion_checks(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Execute registered verification commands in the original task workspace."""

    results: List[Dict[str, Any]] = []
    for item in state["requirements"]:
        command = item.get("check_command")
        if not command:
            continue
        result: Dict[str, Any] = {
            "requirement_id": item["id"],
            "command": command,
            "ran_at": timestamp(),
            "exit_code": None,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
        }
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=state["workspace"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            result.update(
                {
                    "exit_code": completed.returncode,
                    "stdout": output_tail(completed.stdout),
                    "stderr": output_tail(completed.stderr),
                }
            )
        except subprocess.TimeoutExpired as exc:
            result.update(
                {
                    "timed_out": True,
                    "stdout": output_tail(exc.stdout),
                    "stderr": output_tail(exc.stderr),
                }
            )
        except OSError as exc:
            result["stderr"] = str(exc)
        item["last_check"] = result
        results.append(result)
    return results


def summary(state: Dict[str, Any], path: Path) -> Dict[str, Any]:
    verified = sum(item["status"] == "verified" for item in state["requirements"])
    return {
        "objective": state["objective"],
        "status": state["status"],
        "state_path": str(path),
        "requirements": {
            "total": len(state["requirements"]),
            "verified": verified,
            "unverified": len(state["requirements"]) - verified,
        },
        "attempts": {
            "total": len(state["attempts"]),
            "in_progress": active_attempt(state)["id"] if active_attempt(state) else None,
        },
        "lessons": len(state["lessons"]),
        "reviews": len(state["reviews"]),
        "review_reasons": review_reasons(state) if state["status"] == ACTIVE else [],
        "completion_blockers": completion_blockers(state),
    }


def blank_state(objective: str, session_id: Optional[str]) -> Dict[str, Any]:
    created = timestamp()
    return {
        "version": STATE_VERSION,
        "objective": objective,
        "status": ACTIVE,
        "session_id": session_id or os.environ.get("CLAUDE_SESSION_ID"),
        "workspace": str(Path.cwd().resolve()),
        "created_at": created,
        "updated_at": created,
        "requirements": [],
        "attempts": [],
        "lessons": [],
        "reviews": [],
        "last_review_attempt_id": 0,
        "completion": None,
        "stop": None,
    }


def cmd_init(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    archived = archive_inactive_state(path)
    state = blank_state(required_text(args.objective, "objective"), args.session)
    save_state(path, state, "task_initialized", {"objective": state["objective"]})
    result = summary(state, path)
    if archived:
        result["archived_previous_state"] = archived
    return result


def cmd_requirement_add(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    state = load_state(path)
    require_active(state)
    requirement_id = required_text(args.id, "id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", requirement_id):
        raise CommandError("requirement id must be 1-64 letters, digits, underscores, or hyphens")
    if any(item["id"] == requirement_id for item in state["requirements"]):
        raise CommandError(f"Requirement {requirement_id} already exists")
    item = {
        "id": requirement_id,
        "description": required_text(args.description, "description"),
        "evidence_required": required_text(args.evidence_required, "evidence-required"),
        "current": bool(args.current),
        "max_age_minutes": args.max_age_minutes,
        "check_command": args.check_command.strip() if args.check_command else None,
        "last_check": None,
        "status": "unverified",
        "evidence": [],
        "sources": [],
        "freshness_note": None,
        "verified_at": None,
        "invalidation": None,
    }
    state["requirements"].append(item)
    save_state(path, state, "requirement_added", {"id": requirement_id})
    return summary(state, path)


def cmd_requirement_verify(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    state = load_state(path)
    require_active(state)
    item = requirement(state, args.id)
    evidence = [required_text(value, "evidence") for value in args.evidence]
    sources = [required_text(value, "source") for value in (args.source or [])]
    freshness_note = args.freshness_note.strip() if args.freshness_note else None
    if item["current"] and not sources:
        raise CommandError(f"{item['id']} is current-sensitive; at least one --source is required")
    if item["current"] and not freshness_note:
        raise CommandError(f"{item['id']} is current-sensitive; --freshness-note is required")
    item.update(
        {
            "status": "verified",
            "evidence": evidence,
            "sources": sources,
            "freshness_note": freshness_note,
            "verified_at": timestamp(),
            "invalidation": None,
        }
    )
    save_state(path, state, "requirement_verified", {"id": item["id"], "evidence": evidence})
    return summary(state, path)


def cmd_requirement_unverify(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    state = load_state(path)
    require_active(state)
    item = requirement(state, args.id)
    reason = required_text(args.reason, "reason")
    item.update(
        {
            "status": "unverified",
            "evidence": [],
            "sources": [],
            "freshness_note": None,
            "verified_at": None,
            "invalidation": {"at": timestamp(), "reason": reason},
        }
    )
    save_state(path, state, "requirement_invalidated", {"id": item["id"], "reason": reason})
    return summary(state, path)


def cmd_attempt_start(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    state = load_state(path)
    require_active(state)
    current = active_attempt(state)
    if current:
        raise CommandError(f"Attempt {current['id']} is already in progress; record its outcome first")
    reasons = review_reasons(state)
    if reasons:
        raise CommandError("A meta-review is required before another attempt", code=3, details=reasons)

    strategy = required_text(args.strategy, "strategy")
    change = required_text(args.change, "change")
    signature = (normalized(strategy), normalized(change))
    for previous in state["attempts"]:
        if previous.get("outcome") != "failed":
            continue
        previous_signature = (normalized(previous["strategy"]), normalized(previous["change"]))
        if signature == previous_signature:
            raise CommandError(
                f"Attempt {previous['id']} already failed with the same strategy and change; "
                "use the recorded lesson and choose a materially different approach",
                code=3,
            )

    attempt = {
        "id": max((item["id"] for item in state["attempts"]), default=0) + 1,
        "strategy": strategy,
        "hypothesis": required_text(args.hypothesis, "hypothesis"),
        "prediction": required_text(args.prediction, "prediction"),
        "change": change,
        "status": IN_PROGRESS,
        "outcome": None,
        "started_at": timestamp(),
        "finished_at": None,
    }
    state["attempts"].append(attempt)
    save_state(path, state, "attempt_started", {"id": attempt["id"], "strategy": strategy})
    result = summary(state, path)
    result["attempt"] = attempt
    return result


def cmd_attempt_end(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    state = load_state(path)
    require_active(state)
    attempt = next(
        (
            item
            for item in state["attempts"]
            if item["id"] == args.attempt_id and item["status"] == IN_PROGRESS
        ),
        None,
    )
    if not attempt:
        raise CommandError(f"No in-progress attempt has id {args.attempt_id}", code=4)
    observation = required_text(args.observation, "observation")
    cause = required_text(args.cause, "cause")
    lesson_text = required_text(args.lesson, "lesson")
    scope = required_text(args.scope, "scope")
    attempt.update(
        {
            "status": FINISHED,
            "outcome": args.outcome,
            "observation": observation,
            "cause": cause,
            "finished_at": timestamp(),
        }
    )
    lesson = {
        "id": len(state["lessons"]) + 1,
        "attempt_id": attempt["id"],
        "lesson": lesson_text,
        "scope": scope,
        "evidence": observation,
        "created_at": timestamp(),
    }
    state["lessons"].append(lesson)
    save_state(
        path,
        state,
        "attempt_finished",
        {"id": attempt["id"], "outcome": args.outcome, "lesson_id": lesson["id"]},
    )
    result = summary(state, path)
    result["lesson"] = lesson
    return result


def cmd_review(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    state = load_state(path)
    require_active(state)
    current = active_attempt(state)
    if current:
        raise CommandError(f"Finish or interrupt attempt {current['id']} before reviewing")
    review = {
        "id": len(state["reviews"]) + 1,
        "at": timestamp(),
        "patterns": required_text(args.patterns, "patterns"),
        "weakest_assumption": required_text(args.weakest_assumption, "weakest-assumption"),
        "stop_doing": required_text(args.stop_doing, "stop-doing"),
        "start_doing": required_text(args.start_doing, "start-doing"),
        "keep_doing": required_text(args.keep_doing, "keep-doing"),
        "probe": required_text(args.probe, "probe"),
        "next_actions": [required_text(value, "next-action") for value in args.next_action],
    }
    state["reviews"].append(review)
    state["last_review_attempt_id"] = max(
        (item["id"] for item in state["attempts"]), default=0
    )
    save_state(path, state, "meta_review_recorded", {"id": review["id"]})
    result = summary(state, path)
    result["review"] = review
    return result


def cmd_complete(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    state = load_state(path)
    require_active(state)
    blockers = completion_blockers(state)
    if blockers:
        raise CommandError("Completion gate failed", code=5, details=blockers)

    checks = run_completion_checks(state)
    failures: List[str] = []
    by_requirement = {item["id"]: item for item in state["requirements"]}
    for result in checks:
        if result["exit_code"] == 0:
            continue
        item = by_requirement[result["requirement_id"]]
        reason = (
            f"completion check timed out after 120 seconds: {result['command']}"
            if result["timed_out"]
            else f"completion check exited {result['exit_code']}: {result['command']}"
        )
        item.update(
            {
                "status": "unverified",
                "evidence": [],
                "sources": [],
                "freshness_note": None,
                "verified_at": None,
                "invalidation": {"at": timestamp(), "reason": reason},
            }
        )
        output = result["stderr"] or result["stdout"]
        failures.append(f"{item['id']}: {reason}" + (f"; output: {output}" if output else ""))
    if failures:
        save_state(path, state, "completion_checks_failed", {"checks": checks})
        raise CommandError("Completion verification commands failed", code=5, details=failures)

    state["status"] = COMPLETED
    state["completion"] = {
        "at": timestamp(),
        "summary": required_text(args.summary, "summary"),
        "checks": checks,
    }
    save_state(
        path,
        state,
        "task_completed",
        {"summary": state["completion"]["summary"], "checks": checks},
    )
    return summary(state, path)


def cmd_stop(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    # Preserve user control even if the skill was invoked but setup had not begun.
    state = (
        load_state(path)
        if path.exists()
        else blank_state("User stopped before task initialization", args.session)
    )
    require_active(state)
    request = required_text(args.user_request, "user-request")
    for attempt in state["attempts"]:
        if attempt["status"] == IN_PROGRESS:
            attempt.update(
                {
                    "status": INTERRUPTED,
                    "outcome": INTERRUPTED,
                    "observation": "Attempt interrupted by an explicit user stop",
                    "finished_at": timestamp(),
                }
            )
    state["status"] = STOPPED
    state["stop"] = {"at": timestamp(), "user_request": request}
    save_state(path, state, "task_stopped_by_user", {"user_request": request})
    return summary(state, path)


def cmd_resume(args: argparse.Namespace, path: Path) -> Dict[str, Any]:
    state = load_state(path)
    if state["status"] != STOPPED:
        raise CommandError(f"Only a stopped task can be resumed; current status is {state['status']}")
    state["status"] = ACTIVE
    state["stop"] = None
    save_state(path, state, "task_resumed")
    return summary(state, path)


def positive_minutes(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", help="state file; defaults to a session/workspace-specific path")
    parser.add_argument("--session", help="session id used to derive the default state path")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="initialize a new active task")
    init.add_argument("--objective", required=True)
    init.set_defaults(handler=cmd_init)

    add = commands.add_parser("requirement-add", help="register an atomic completion requirement")
    add.add_argument("--id", required=True)
    add.add_argument("--description", required=True)
    add.add_argument("--evidence-required", required=True)
    add.add_argument("--current", action="store_true", help="require current-source evidence")
    add.add_argument("--max-age-minutes", type=positive_minutes, default=60)
    add.add_argument(
        "--check-command",
        help="shell command that complete must rerun successfully in the task workspace",
    )
    add.set_defaults(handler=cmd_requirement_add)

    verify = commands.add_parser("requirement-verify", help="attach evidence and verify a requirement")
    verify.add_argument("--id", required=True)
    verify.add_argument("--evidence", action="append", required=True)
    verify.add_argument("--source", action="append")
    verify.add_argument("--freshness-note")
    verify.set_defaults(handler=cmd_requirement_verify)

    unverify = commands.add_parser("requirement-unverify", help="invalidate a previous verification")
    unverify.add_argument("--id", required=True)
    unverify.add_argument("--reason", required=True)
    unverify.set_defaults(handler=cmd_requirement_unverify)

    start = commands.add_parser("attempt-start", help="start a predicted, non-duplicate attempt")
    start.add_argument("--strategy", required=True)
    start.add_argument("--hypothesis", required=True)
    start.add_argument("--prediction", required=True)
    start.add_argument("--change", required=True)
    start.set_defaults(handler=cmd_attempt_start)

    end = commands.add_parser("attempt-end", help="record observations and a scoped lesson")
    end.add_argument("--attempt-id", type=int, required=True)
    end.add_argument("--outcome", choices=("failed", "partial", "succeeded"), required=True)
    end.add_argument("--observation", required=True)
    end.add_argument("--cause", required=True)
    end.add_argument("--lesson", required=True)
    end.add_argument("--scope", required=True)
    end.set_defaults(handler=cmd_attempt_end)

    review = commands.add_parser("review", help="record a mandatory strategy meta-review")
    review.add_argument("--patterns", required=True)
    review.add_argument("--weakest-assumption", required=True)
    review.add_argument("--stop-doing", required=True)
    review.add_argument("--start-doing", required=True)
    review.add_argument("--keep-doing", required=True)
    review.add_argument("--probe", required=True)
    review.add_argument("--next-action", action="append", required=True)
    review.set_defaults(handler=cmd_review)

    status = commands.add_parser("status", help="show machine-readable progress and gates")
    status.set_defaults(handler=lambda args, path: summary(load_state(path), path))

    complete = commands.add_parser("complete", help="complete only if every executable gate passes")
    complete.add_argument("--summary", required=True)
    complete.set_defaults(handler=cmd_complete)

    stop = commands.add_parser("stop", help="record an explicit user stop, pause, or redirect")
    stop.add_argument("--user-request", required=True)
    stop.set_defaults(handler=cmd_stop)

    resume = commands.add_parser("resume", help="resume a user-stopped task")
    resume.set_defaults(handler=cmd_resume)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.state:
            path = Path(args.state).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
        else:
            path = default_state_path(session_id=args.session)
        result = args.handler(args, path)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
        return 0
    except CommandError as exc:
        error: Dict[str, Any] = {"ok": False, "error": str(exc)}
        if exc.details is not None:
            error["details"] = exc.details
        print(json.dumps(error, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return exc.code
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
