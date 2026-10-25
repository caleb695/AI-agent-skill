# Relentless

An [Agent Skills](https://agentskills.io)-compatible skill for persistent, adaptive, and evidence-verified AI-agent execution.

Relentless tells an agent to keep making useful progress until every requirement is verified or the user explicitly stops, pauses, or redirects the task. It is designed to prevent both common failure modes: giving up too early and repeating the same failed approach indefinitely.

## What the skill enforces

- **No voluntary give-up response.** Errors, dead ends, uncertainty, and even suspected impossibility trigger diagnosis and another approach—not a final “I couldn't.”
- **Adaptive retries.** An attempt ledger records what failed and why. Repeated failure within one strategy family triggers a meaningful change in source, tool, hypothesis, decomposition, or implementation.
- **Requirement-level completion.** The agent builds a checklist from the original request and does not silently drop constraints or pass off a close match as success.
- **Thorough verification.** Claims require inspected evidence, code requires relevant checks, and important contradictions must be investigated.
- **Current information.** Time-sensitive claims are checked against live or recently updated sources; stale pages and search snippets are not treated as proof of the present.
- **Honest status.** The agent must never invent progress, tests, citations, or completion. If the user stops the work, the agent can report an unresolved checkpoint without calling it done.

For website-discovery requests, the skill specifically requires a candidate-by-requirement matrix. A website is a match only when **every** mandatory requirement has current supporting evidence.

## Installation

The repository root is the skill directory; [`SKILL.md`](SKILL.md) contains the complete skill. Install it in any agent that supports the Agent Skills format by copying it into a skill directory named `relentless`.

### Claude Code: project scope

Run from the project where you want the skill available:

```sh
mkdir -p .claude/skills/relentless
curl -fsSL https://raw.githubusercontent.com/caleb695/AI-agent-skill/main/SKILL.md \
  -o .claude/skills/relentless/SKILL.md
```

Commit `.claude/skills/relentless/SKILL.md` to share it with everyone working on that project.

### Claude Code: personal scope

```sh
mkdir -p ~/.claude/skills/relentless
curl -fsSL https://raw.githubusercontent.com/caleb695/AI-agent-skill/main/SKILL.md \
  -o ~/.claude/skills/relentless/SKILL.md
```

### Other compatible agents

Copy `SKILL.md` to `<your-skills-directory>/relentless/SKILL.md`, then follow the agent's skill discovery or reload instructions. If the agent does not select the skill automatically, invoke it explicitly:

```text
Use the relentless skill to find a currently available website that meets all of these requirements: ...
```

The skill governs behavior within an agent session. It cannot override host-enforced execution limits or grant tools and permissions the agent does not have.

## Example behavior

For a request to find a website with six requirements, the agent should:

1. Turn all six requirements and exclusions into a checklist.
2. Search using multiple terminology and source strategies.
3. Inspect candidates directly instead of trusting snippets.
4. Record unknown and failed requirements honestly.
5. When searches stall, identify why and change the query, source class, decomposition, language, or discovery method.
6. Recheck a successful candidate's live site and current evidence before calling it a match.
7. Continue with a different approach if no fully verified match has been found and the user has not stopped the task.

## Skill design

`SKILL.md` is self-contained and uses only portable Markdown and Agent Skills frontmatter. It defines:

1. a requirement ledger and explicit definition of done;
2. an inspect → choose → act → verify → record → adapt loop;
3. failure diagnosis and anti-repetition rules;
4. research, debugging, and complex-task strategy families;
5. coverage, evidence, correctness, and freshness checks; and
6. strict truthfulness rules for progress, completion, and user-requested checkpoints.
