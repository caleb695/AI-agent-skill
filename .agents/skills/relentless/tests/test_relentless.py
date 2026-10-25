from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "relentless.py"
HOOK = ROOT / "scripts" / "stop_hook.py"
UNSET = object()


class RelentlessCLITest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state.json"

    def cli(
        self,
        *arguments: str,
        expected: int = 0,
        state: Path | None | object = UNSET,
        session: str | None = None,
        env: dict[str, str] | None = None,
    ) -> dict:
        command = [sys.executable, str(CLI)]
        selected_state = self.state if state is UNSET else state
        if selected_state is not None:
            command.extend(["--state", str(selected_state)])
        if session:
            command.extend(["--session", session])
        command.extend(arguments)
        environment = os.environ.copy()
        if env:
            environment.update(env)
        result = subprocess.run(command, text=True, capture_output=True, check=False, env=environment)
        self.assertEqual(
            result.returncode,
            expected,
            msg=f"command: {command}\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        output = result.stdout if result.stdout.strip() else result.stderr
        return json.loads(output)

    def hook(self, **overrides: str | bool) -> dict:
        payload = {
            "session_id": "test-session",
            "cwd": str(ROOT),
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            **overrides,
        }
        environment = os.environ.copy()
        environment["RELENTLESS_STATE"] = str(self.state)
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def init(self, objective: str = "Test objective") -> dict:
        return self.cli("init", "--objective", objective)

    def add_requirement(self, current: bool = False) -> None:
        arguments = [
            "requirement-add",
            "--id",
            "R1",
            "--description",
            "The result works",
            "--evidence-required",
            "Direct observation of a successful run",
        ]
        if current:
            arguments.append("--current")
        self.cli(*arguments)

    def start_attempt(
        self,
        strategy: str = "search-primary-sources",
        change: str = "Initial query",
        expected: int = 0,
    ) -> dict:
        return self.cli(
            "attempt-start",
            "--strategy",
            strategy,
            "--hypothesis",
            "This approach will produce decision-relevant evidence",
            "--prediction",
            "The observation will support or reject the hypothesis",
            "--change",
            change,
            expected=expected,
        )

    def end_attempt(self, attempt_id: int = 1, outcome: str = "failed") -> dict:
        return self.cli(
            "attempt-end",
            "--attempt-id",
            str(attempt_id),
            "--outcome",
            outcome,
            "--observation",
            "The actual result differed from the prediction",
            "--cause",
            "The query vocabulary did not match primary-source terminology",
            "--lesson",
            "Use terminology from primary documentation",
            "--scope",
            "Searches in this problem domain",
        )

    def review(self) -> dict:
        return self.cli(
            "review",
            "--patterns",
            "Two searches returned the same irrelevant sources",
            "--weakest-assumption",
            "The current vocabulary matches the domain",
            "--stop-doing",
            "Cosmetic keyword variations",
            "--start-doing",
            "Primary-source taxonomy discovery",
            "--keep-doing",
            "Direct evidence checks",
            "--probe",
            "Inspect one authoritative terminology page",
            "--next-action",
            "Build a new query from the discovered taxonomy",
        )

    def verify(self, current: bool = False) -> dict:
        arguments = [
            "requirement-verify",
            "--id",
            "R1",
            "--evidence",
            "Observed the expected behavior directly",
        ]
        if current:
            arguments.extend(
                [
                    "--source",
                    "https://example.com/current-primary-source",
                    "--freshness-note",
                    "The live primary source was inspected during this verification",
                ]
            )
        return self.cli(*arguments)

    def test_completion_requires_evidence_and_writes_audit_events(self) -> None:
        self.init()
        blocked = self.cli("complete", "--summary", "Premature", expected=5)
        self.assertIn("no requirements", blocked["details"][0])

        self.add_requirement()
        blocked = self.cli("complete", "--summary", "Still premature", expected=5)
        self.assertIn("R1 is unverified", blocked["details"][0])

        self.verify()
        completed = self.cli("complete", "--summary", "Verified result")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["completion_blockers"], [])
        events = [json.loads(line) for line in (Path(str(self.state) + ".events.jsonl")).read_text().splitlines()]
        self.assertEqual(
            [event["type"] for event in events],
            ["task_initialized", "requirement_added", "requirement_verified", "task_completed"],
        )

    def test_current_requirement_needs_source_freshness_and_unexpired_verification(self) -> None:
        self.init()
        self.add_requirement(current=True)
        self.cli("requirement-verify", "--id", "R1", "--evidence", "Observed it", expected=2)
        self.cli(
            "requirement-verify",
            "--id",
            "R1",
            "--evidence",
            "Observed it",
            "--source",
            "https://example.com/live",
            expected=2,
        )
        self.verify(current=True)

        state = json.loads(self.state.read_text())
        state["requirements"][0]["verified_at"] = "2000-01-01T00:00:00Z"
        self.state.write_text(json.dumps(state))
        blocked = self.cli("complete", "--summary", "Stale result", expected=5)
        self.assertTrue(any("stale" in item for item in blocked["details"]))

    def test_completion_executes_registered_verification_command(self) -> None:
        self.init()
        self.cli(
            "requirement-add",
            "--id",
            "R1",
            "--description",
            "The executable check passes",
            "--evidence-required",
            "A zero exit status",
            "--check-command",
            f'{sys.executable} -c "print(\'check ran\')"',
        )
        self.verify()
        completed = self.cli("complete", "--summary", "Executable check passed")
        self.assertEqual(completed["status"], "completed")
        state = json.loads(self.state.read_text())
        self.assertEqual(state["requirements"][0]["last_check"]["exit_code"], 0)
        self.assertEqual(state["requirements"][0]["last_check"]["stdout"], "check ran\n")

    def test_failed_completion_command_reopens_requirement(self) -> None:
        self.init()
        self.cli(
            "requirement-add",
            "--id",
            "R1",
            "--description",
            "The executable check passes",
            "--evidence-required",
            "A zero exit status",
            "--check-command",
            f'{sys.executable} -c "import sys; print(\'failed\'); sys.exit(7)"',
        )
        self.verify()
        blocked = self.cli("complete", "--summary", "Must not complete", expected=5)
        self.assertIn("exited 7", blocked["details"][0])
        state = json.loads(self.state.read_text())
        self.assertEqual(state["requirements"][0]["status"], "unverified")
        self.assertEqual(state["requirements"][0]["last_check"]["exit_code"], 7)

    def test_attempt_must_be_closed_and_only_one_can_run(self) -> None:
        self.init()
        self.add_requirement()
        started = self.start_attempt()
        self.assertEqual(started["attempt"]["id"], 1)
        self.start_attempt(change="Another approach", expected=2)
        self.verify()
        blocked = self.cli("complete", "--summary", "Attempt still open", expected=5)
        self.assertIn("attempt 1 is still in progress", blocked["details"])
        self.end_attempt(outcome="succeeded")
        self.cli("complete", "--summary", "Closed and verified")

    def test_exact_failed_retry_is_rejected_but_meaningful_change_is_allowed(self) -> None:
        self.init()
        self.start_attempt(change="Query alpha")
        self.end_attempt()
        duplicate = self.start_attempt(change="  query   ALPHA ", expected=3)
        self.assertIn("already failed", duplicate["error"])
        changed = self.start_attempt(change="Query beta using primary-source taxonomy")
        self.assertEqual(changed["attempt"]["id"], 2)

    def test_two_failures_in_one_family_force_structured_review(self) -> None:
        self.init()
        for attempt_id, change in ((1, "Query alpha"), (2, "Query beta")):
            self.start_attempt(change=change)
            self.end_attempt(attempt_id)
        blocked = self.start_attempt(strategy="different-family", change="Direct registry", expected=3)
        self.assertIn("meta-review", blocked["error"])
        reviewed = self.review()
        self.assertEqual(reviewed["reviews"], 1)
        self.assertEqual(reviewed["review_reasons"], [])
        started = self.start_attempt(strategy="different-family", change="Direct registry")
        self.assertEqual(started["attempt"]["id"], 3)

    def test_unverify_invalidates_previous_completion_evidence(self) -> None:
        self.init()
        self.add_requirement()
        self.verify()
        invalidated = self.cli(
            "requirement-unverify",
            "--id",
            "R1",
            "--reason",
            "Contradictory current evidence appeared",
        )
        self.assertEqual(invalidated["requirements"]["unverified"], 1)
        self.cli("complete", "--summary", "Must fail", expected=5)

    def test_explicit_stop_interrupts_attempt_and_resume_preserves_history(self) -> None:
        self.init()
        self.add_requirement()
        self.start_attempt()
        stopped = self.cli("stop", "--user-request", "Please stop now")
        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual(stopped["completion_blockers"], [])
        state = json.loads(self.state.read_text())
        self.assertEqual(state["attempts"][0]["status"], "interrupted")
        self.cli("complete", "--summary", "Cannot complete stopped task", expected=3)
        resumed = self.cli("resume")
        self.assertEqual(resumed["status"], "active")
        self.assertEqual(resumed["attempts"]["total"], 1)
        self.assertIsNone(resumed["attempts"]["in_progress"])

    def test_new_task_archives_inactive_state(self) -> None:
        self.init("First task")
        self.cli("stop", "--user-request", "Move on")
        second = self.init("Second task")
        archive = Path(second["archived_previous_state"])
        self.assertTrue(archive.exists())
        self.assertEqual(json.loads(archive.read_text())["objective"], "First task")
        self.assertEqual(second["objective"], "Second task")

    def test_session_default_path_is_durable_across_processes(self) -> None:
        environment = {"RELENTLESS_STATE_HOME": str(self.root / "state-home")}
        first = self.cli(
            "init",
            "--objective",
            "Session state",
            state=None,
            session="session-abc",
            env=environment,
        )
        second = self.cli("status", state=None, session="session-abc", env=environment)
        self.assertEqual(first["state_path"], second["state_path"])
        self.assertTrue(Path(first["state_path"]).exists())
        self.assertEqual(second["objective"], "Session state")

    def test_hook_blocks_missing_incomplete_and_unrecorded_completion(self) -> None:
        missing = self.hook()
        self.assertEqual(missing["decision"], "block")
        self.assertIn("no durable task state", missing["reason"])

        self.init()
        self.add_requirement()
        active = self.hook()
        self.assertEqual(active["decision"], "block")
        self.assertIn("R1 is unverified", active["reason"])

        self.verify()
        ready = self.hook(stop_hook_active=True)
        self.assertEqual(ready["decision"], "block")
        self.assertIn("complete --summary", ready["reason"])
        self.assertIn("make a tool call", ready["reason"])

        self.cli("complete", "--summary", "Verified")
        self.assertEqual(self.hook(), {})

    def test_hook_allows_explicit_user_stop(self) -> None:
        self.init()
        self.cli("stop", "--user-request", "Stop")
        self.assertEqual(self.hook(), {})

    def test_user_can_stop_even_before_task_initialization(self) -> None:
        stopped = self.cli("stop", "--user-request", "Do not start")
        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual(self.hook(), {})

    def test_hook_does_not_block_an_unrelated_session_for_shared_state(self) -> None:
        self.cli("init", "--objective", "Session-specific", session="owner-session")
        self.assertEqual(self.hook(session_id="other-session"), {})
        self.assertEqual(self.hook(session_id="owner-session")["decision"], "block")

    def test_damaged_state_fails_closed_with_valid_hook_json(self) -> None:
        self.state.write_text("not json")
        result = self.hook()
        self.assertEqual(result["decision"], "block")
        self.assertIn("could not be loaded", result["reason"])


if __name__ == "__main__":
    unittest.main()
