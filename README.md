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

The skill lives in the standard Agent Skills directory (`.agents/skills/<skill-name>/`) used by OpenHands, GitHub Copilot, Codex, Cursor, and other compatible hosts:

```text
.agents/skills/relentless/SKILL.md                    Skill instructions and Claude Code Stop-hook registration
.agents/skills/relentless/scripts/relentless.py       Durable controller and executable gates
.agents/skills/relentless/scripts/stop_hook.py        Runtime Stop enforcement backed by controller state
.agents/skills/relentless/tests/                      End-to-end CLI and hook tests
AGENTS.md                                             Guidance for agents working inside this repository
README.md
```

## Requirements

- Python 3.10 or newer; no third-party Python packages are required.
- For automatic runtime Stop enforcement: a Claude Code version that supports hooks in skill frontmatter.
- Other Agent Skills hosts (including OpenHands and OpenHands Cloud) can use the controller directly, but do not provide the Claude Code hook's runtime enforcement unless they implement an equivalent integration.

## OpenHands Cloud

The skill works in [OpenHands Cloud](https://docs.openhands.dev/overview/skills) with no extra tooling. Pick whichever flow fits:

### Option 1: Use this repository as the workspace

Start an OpenHands Cloud conversation on `caleb695/AI-agent-skill` (or any repo/fork that contains `.agents/skills/relentless/`). OpenHands discovers project skills from `.agents/skills/` automatically, advertises `relentless` in the available-skills catalog, and loads the full skill when the task matches. Say "use the relentless skill" (or just give it a hard task that matches the description) to invoke it.

### Option 2: Download the skill into another workspace

In any OpenHands Cloud conversation, run the built-in [`/add-skill`](https://docs.openhands.dev/overview/skills/adding) command:

```text
/add-skill https://github.com/caleb695/AI-agent-skill/tree/main/.agents/skills/relentless
```

This copies the whole skill (including `scripts/`) into `<workspace>/.agents/skills/relentless/`. Start a **new** conversation afterward so OpenHands rebuilds the skill catalog.

### Option 3: One-click launch link

Share this link to open OpenHands Cloud with the skill pre-configured from this repository (the user confirms trust before it loads):

```text
https://app.all-hands.dev/launch?plugins=W3sic291cmNlIjoiZ2l0aHViOmNhbGViNjk1L0FJLWFnZW50LXNraWxsIiwicmVmIjoibWFpbiIsInJlcG9fcGF0aCI6Ii5hZ2VudHMvc2tpbGxzL3JlbGVudGxlc3MifV0=
```

The `plugins` parameter is the base64-encoded JSON `[{"source":"github:caleb695/AI-agent-skill","ref":"main","repo_path":".agents/skills/relentless"}]` (see the [Plugin Launcher docs](https://docs.openhands.dev/openhands/usage/cloud/plugin-launcher)).

### Option 4: Make it available in every repository

OpenHands loads user skills from a `.agents` repository under your GitHub account. Create a repository named `.agents`, add a `skills/` directory, and copy `.agents/skills/relentless/` into it as `skills/relentless/`. OpenHands then loads the skill for all your conversations, in any repo.

### Honest limits on OpenHands

OpenHands does not implement Claude Code's Stop hook, so the `hooks:` frontmatter is ignored there and **runtime stop enforcement is unavailable**. The controller CLI still enforces every other gate (state, evidence, retries, reviews, freshness, completion), and the skill instructs the agent to say so honestly. Invoke the controller as `python3 .agents/skills/relentless/scripts/relentless.py ...`; with no session ID it derives a workspace-specific state file automatically.

## Claude Code installation

Claude Code reads skills from `.claude/skills/`, so copy the skill directory there. Install the **whole skill**, including `scripts/`; copying only `SKILL.md` leaves out the enforcement layer.

### Project scope

Run from the project where you want the skill available:

```sh
tmp="$(mktemp -d)"
curl -fsSL https://codeload.github.com/caleb695/AI-agent-skill/tar.gz/refs/heads/main \
  | tar -xz -C "$tmp"
mkdir -p .claude/skills/relentless
cp -R "$tmp/AI-agent-skill-main/.agents/skills/relentless/." .claude/skills/relentless/
rm -r "$tmp"
```

Commit `.claude/skills/relentless/` to share the skill with the project. Invoke it explicitly with `/relentless` or ask the agent to use the relentless skill. The Stop hook registers when the skill is invoked and remains registered for that session.

### Personal scope

```sh
tmp="$(mktemp -d)"
curl -fsSL https://codeload.github.com/caleb695/AI-agent-skill/tar.gz/refs/heads/main \
  | tar -xz -C "$tmp"
mkdir -p ~/.claude/skills/relentless
cp -R "$tmp/AI-agent-skill-main/.agents/skills/relentless/." ~/.claude/skills/relentless/
rm -r "$tmp"
```

## Other compatible agents

Copy the contents of `.agents/skills/relentless/` (the `SKILL.md` plus the `scripts/` directory) into your host's skills directory as `<your-skills-directory>/relentless/`, then follow the host's skill discovery instructions. Use the actual bundled script path when running controller commands. The skill remains useful without hook support, but the agent must accurately acknowledge that runtime Stop enforcement is unavailable.

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
python3 .agents/skills/relentless/scripts/relentless.py --state /tmp/my-task.json init \
  --objective "Implement and verify the requested feature"

python3 .agents/skills/relentless/scripts/relentless.py --state /tmp/my-task.json requirement-add \
  --id R1 \
  --description "The requested behavior passes its regression test" \
  --evidence-required "A passing run of the focused regression test" \
  --check-command "python3 -m pytest tests/test_feature.py -q"
```

Global options such as `--state` and `--session` come **before** the subcommand. Run `python3 .agents/skills/relentless/scripts/relentless.py --help` or `<command> --help` for the complete interface.

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
python3 .agents/skills/relentless/scripts/relentless.py --session "<session-id>" stop \
  --user-request "The user's explicit stop, pause, or redirect"
```

This also works before task initialization, preserving user control. A physical user interrupt does not depend on the controller or hook.

## Runtime-enforcement limits

The Stop hook checks durable state instead of trusting a final “done” message. It deliberately continues to block hook-driven continuations until the agent uses tools to resolve the gates or record completion. Claude Code's own continuation limits, permissions, tool availability, and execution limits still apply; the skill does not bypass them. A host-forced interruption must be reported honestly and never relabeled as successful completion.

## Tests

Run the standard-library test suite:

```sh
python3 -m unittest discover -s .agents/skills/relentless/tests -v
```

The tests exercise the real CLI and Stop-hook subprocesses, including successful completion, missing evidence, current-source freshness, executable check failure, duplicate retries, mandatory reviews, state persistence, user stop/resume, missing or damaged state, and unrelated-session isolation. They also assert the OpenHands/Agent Skills layout (`.agents/skills/relentless/SKILL.md` with a directory-matching name and keyword triggers) so the skill keeps installing correctly.
