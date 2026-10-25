# Relentless

A persistent, self-improving AI-agent skill with **executable enforcement**, not just prompting.

Relentless combines an [Agent Skills](https://agentskills.io)-compatible `SKILL.md` with a standard-library Python controller and a Claude Code Stop hook. The agent continues until every requirement passes the controller's completion gate or the user explicitly stops, pauses, or redirects the task.

## Why this is stronger than a prompt-only skill

| Layer | What it does |
| --- | --- |
| Runtime Stop hook | On supported Claude Code versions, blocks a normal stop when the invoked skill has no task state, requirements remain unresolved, a review is required, or completion has not been recorded. |
| Durable state machine | Persists requirements, attempts, observations, scoped lessons, reviews, verification, stop, and completion across tool calls and context compaction. |
| Completion gate | Refuses completion with missing evidence, unverified requirements, stale current-source checks, open attempts, or mandatory reviews. |
| Real verification commands | Optionally reruns a requirement's actual test or check command at completion. A failure or timeout reopens that requirement. |
| Retry enforcement | Rejects an exact strategy-and-change pair that already failed and prevents overlapping attempts. |
| Improvement enforcement | Requires structured meta-reviews after repeated failures or prolonged lack of verified progress before another attempt can start. |
| Audit trail | Uses atomic JSON state writes and an append-only JSONL event log instead of relying on conversational memory. |
| Reasoning playbook | Guides failure diagnosis, strategy changes, source inspection, freshness checks, and honest reporting. |

The controller cannot independently judge arbitrary natural-language evidence, so the agent must still be honest when supplying observations and sources. It **can** deterministically prevent missing state, skipped evidence fields, stale checks, repeated failed attempts, unrecorded reviews, and premature completion—and it can execute real checks for testable requirements.

## Repository layout

```text
SKILL.md                    Skill instructions and Claude Code Stop-hook registration
scripts/relentless.py       Durable controller and executable gates
scripts/stop_hook.py        Runtime Stop enforcement backed by controller state
tests/test_relentless.py    End-to-end CLI and hook tests
```

## Requirements

- Python 3.10 or newer; no third-party Python packages are required.
- For automatic runtime Stop enforcement: a Claude Code version that supports hooks in skill frontmatter.
- Other Agent Skills hosts can use the controller directly, but do not provide the Claude Code hook's runtime enforcement unless they implement an equivalent integration.

## Installation

Install the **whole skill**, including `scripts/`. Copying only `SKILL.md` leaves out the enforcement layer.

### Claude Code: project scope

Run from the project where you want the skill available:

```sh
tmp="$(mktemp -d)"
curl -fsSL https://codeload.github.com/caleb695/AI-agent-skill/tar.gz/refs/heads/main \
  | tar -xz -C "$tmp"
mkdir -p .claude/skills/relentless
cp -R "$tmp/AI-agent-skill-main/." .claude/skills/relentless/
rm -r "$tmp"
```

Commit `.claude/skills/relentless/` to share the skill with the project. Invoke it explicitly with `/relentless` or ask the agent to use the relentless skill. The Stop hook registers when the skill is invoked and remains registered for that session.

### Claude Code: personal scope

```sh
tmp="$(mktemp -d)"
curl -fsSL https://codeload.github.com/caleb695/AI-agent-skill/tar.gz/refs/heads/main \
  | tar -xz -C "$tmp"
mkdir -p ~/.claude/skills/relentless
cp -R "$tmp/AI-agent-skill-main/." ~/.claude/skills/relentless/
rm -r "$tmp"
```

### Other compatible agents

Copy the repository's `SKILL.md` and `scripts/` directory into `<your-skills-directory>/relentless/`, then follow the host's skill discovery instructions. Use the actual bundled script path when running controller commands. The skill remains useful without hook support, but the agent must accurately acknowledge that runtime Stop enforcement is unavailable.

## Controller workflow

The skill instructs the agent to use this workflow, and the CLI returns machine-readable JSON after every command:

1. `init` — create an active task with the user's actual objective.
2. `requirement-add` — register each atomic requirement and its required evidence.
3. `attempt-start` — record strategy, hypothesis, prediction, and meaningful change before acting.
4. `attempt-end` — record outcome, observation, cause, scoped lesson, and evidence after acting.
5. `review` — satisfy a mandatory improvement gate with patterns, assumptions, stop/start/keep decisions, a probe, and ranked next actions.
6. `requirement-verify` — attach inspected evidence; current-sensitive requirements also need sources and a freshness note.
7. `status` — inspect unresolved gates whenever resuming or after context compaction.
8. `complete` — finish only when all static gates and registered verification commands pass.

Use `requirement-unverify` when new evidence invalidates an earlier verification. Use `resume` only for a user-stopped task the user wants to continue.

### Example with an explicit state file

```sh
python3 scripts/relentless.py --state /tmp/my-task.json init \
  --objective "Implement and verify the requested feature"

python3 scripts/relentless.py --state /tmp/my-task.json requirement-add \
  --id R1 \
  --description "The requested behavior passes its regression test" \
  --evidence-required "A passing run of the focused regression test" \
  --check-command "python3 -m pytest tests/test_feature.py -q"
```

Global options such as `--state` and `--session` come **before** the subcommand. Run `python3 scripts/relentless.py --help` or `<command> --help` for the complete interface.

### Verification-command security

`--check-command` is a shell command executed in the original task workspace when `complete` runs, with a 120-second timeout. Register only trusted commands the agent is permitted to execute. Never construct one from untrusted web content or treat the controller as a sandbox. Captured output is limited to the last 4,000 characters per stream and stored with the check result.

## State and user control

By default, state is stored outside the project:

- With a session ID: a session-specific file under the Relentless state directory.
- Without one: a workspace-specific file.
- Default state directory: `$XDG_STATE_HOME/relentless` when set, otherwise `~/.local/state/relentless`.
- `RELENTLESS_STATE_HOME` overrides the state directory; `RELENTLESS_STATE` or `--state` selects an exact file.

State files and audit logs are written with owner-only permissions. Do not put secrets in objectives, evidence, commands, or notes.

For an explicit conversational stop, the agent records:

```sh
python3 scripts/relentless.py --session "<session-id>" stop \
  --user-request "The user's explicit stop, pause, or redirect"
```

This also works before task initialization, preserving user control. A physical user interrupt does not depend on the controller or hook.

## Runtime-enforcement limits

The Stop hook checks durable state instead of trusting a final “done” message. It deliberately continues to block hook-driven continuations until the agent uses tools to resolve the gates or record completion. Claude Code's own continuation limits, permissions, tool availability, and execution limits still apply; the skill does not bypass them. A host-forced interruption must be reported honestly and never relabeled as successful completion.

## Tests

Run the standard-library test suite:

```sh
python3 -m unittest discover -s tests -v
```

The tests exercise the real CLI and Stop-hook subprocesses, including successful completion, missing evidence, current-source freshness, executable check failure, duplicate retries, mandatory reviews, state persistence, user stop/resume, missing or damaged state, and unrelated-session isolation.
