# AGENTS.md

This repository is an [Agent Skills](https://agentskills.io) package. The skill (`relentless`) lives at `.agents/skills/relentless/` — the standard location OpenHands, OpenHands Cloud, Copilot, Codex, and Cursor discover automatically.

## Rules

- The skill name must match its directory name: `.agents/skills/relentless/SKILL.md` declares `name: relentless`. Keep `SKILL.md`, `scripts/`, and `tests/` inside that directory.
- The skill is self-contained: an installation must include `scripts/relentless.py` and `scripts/stop_hook.py`, never `SKILL.md` alone.
- The `hooks:` frontmatter is Claude Code-specific; other hosts (including OpenHands) ignore it. Never claim runtime Stop enforcement is active on a host without hook support.
- Python 3.10+ standard library only. No third-party runtime dependencies.

## Install / download this skill elsewhere

- OpenHands Cloud (into the current workspace): `/add-skill https://github.com/caleb695/AI-agent-skill/tree/main/.agents/skills/relentless`
- Claude Code: copy the directory to `.claude/skills/relentless/` (project) or `~/.claude/skills/relentless/` (personal).

## Verify changes

```sh
python3 -m unittest discover -s .agents/skills/relentless/tests -v
```
