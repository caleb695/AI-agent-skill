# Relentless

An [Agent Skills](https://agentskills.io)-compatible skill for persistent, self-improving, and evidence-verified AI-agent execution.

Relentless tells an agent to keep making useful progress until every requirement is verified or the user explicitly stops, pauses, or redirects the task. It is designed to prevent three common failure modes: giving up too early, repeating the same failed approach indefinitely, and gaining experience without learning from it.

## What the skill enforces

- **No voluntary give-up response.** Errors, dead ends, uncertainty, and even suspected impossibility trigger diagnosis and another approach—not a final “I couldn't.”
- **Adaptive retries.** An attempt ledger records what failed and why. Repeated failure within one strategy family triggers a meaningful change in source, tool, hypothesis, decomposition, or implementation.
- **Continuous improvement.** The agent predicts outcomes before acting, compares expectations with observations, extracts scoped lessons, and applies them to later decisions. A new attempt must be better informed, not merely different.
- **Process-level learning.** Recurring failures trigger meta-reviews that can improve the problem model, strategy, reusable tooling, or verification checks—not just the next individual attempt.
- **Learning that survives long tasks.** The agent checkpoints its ledgers when the host provides an appropriate mechanism, and never claims cross-session memory without durable storage.
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
2. Before each attempt, predict what the search or inspection should reveal and why.
3. Inspect candidates directly instead of trusting snippets.
4. Record unknown and failed requirements honestly.
5. Compare predictions with results, extract a specific lesson, and update the search model.
6. When searches stall, review patterns across attempts and change the query, source class, decomposition, language, or discovery method based on those lessons.
7. If repeated manual checking is the bottleneck, create a reusable checklist or small tool without weakening verification.
8. Recheck a successful candidate's live site and current evidence before calling it a match.
9. Continue with a better-informed approach if no fully verified match has been found and the user has not stopped the task.

## Skill design

`SKILL.md` is self-contained and uses only portable Markdown and Agent Skills frontmatter. It defines:

1. a requirement ledger and explicit definition of done;
2. an inspect → predict → act → verify → learn → improve loop;
3. failure diagnosis and anti-repetition rules;
4. micro-retrospectives, knowledge ledgers, an improvement ladder, and stall-triggered meta-reviews;
5. research, debugging, and complex-task strategy families;
6. coverage, evidence, correctness, and freshness checks; and
7. strict truthfulness rules for learning, progress, completion, and user-requested checkpoints.
