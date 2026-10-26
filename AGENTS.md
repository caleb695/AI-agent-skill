# AGENTS.md

This repository is an [Agent Skills](https://agentskills.io) package and an OpenHands plugin marketplace. The skill (`relentless`) lives at `.agents/skills/relentless/` — the standard location OpenHands, GitHub Copilot, Codex, Cursor, and other compatible hosts discover for project skills. The root `.plugin/marketplace.json` re-exposes that same directory as an OpenHands marketplace plugin so OpenHands Cloud can load it from the repository root.

## Rules

- The skill name must match its directory name: `.agents/skills/relentless/SKILL.md` declares `name: relentless`. Keep `SKILL.md`, `scripts/`, and `tests/` inside that directory.
- The skill is self-contained: an installation must include `scripts/relentless.py` and `scripts/stop_hook.py`, never `SKILL.md` alone.
- The `hooks:` frontmatter is Claude Code-specific; other hosts (including OpenHands) ignore it. Never claim runtime Stop enforcement is active on a host without hook support.
- Python 3.10+ standard library only. No third-party runtime dependencies.

## Marketplace layout (OpenHands Cloud)

OpenHands reads a repository as a plugin marketplace only when it finds `.plugin/marketplace.json` (or `.claude-plugin/marketplace.json`) at the root, or a top-level `skills/<name>/SKILL.md` folder. Without either, registration fails with "No plugins or skills were found in this repository." Keep these invariants:

- `.plugin/marketplace.json` declares `relentless` with `"source": "./skills/relentless"`.
- `skills` is a symlink to `.agents/skills`. Do not create a second copy of the skill under `skills/`.
- The marketplace source must not point at `.agents/skills/relentless` directly: OpenHands resolves relative plugin sources with `source.lstrip("./")`, which strips the leading dot from `.agents` and would look for `agents/skills/relentless`. The non-dotted `skills/relentless` path is why the symlink exists.
- `.agents/skills/relentless/.plugin/plugin.json` declares `name: relentless`, matching the `SKILL.md` frontmatter.
- `.claude-plugin` and `.codex-plugin` inside the skill directory point at `.plugin`, the layout used by the official OpenHands extensions registry.

## Install / download this skill elsewhere

- OpenHands Cloud marketplace: register `github:caleb695/AI-agent-skill` (ref `main`, no repository path) under Settings > Skills.
- OpenHands Cloud (into the current workspace): `/add-skill https://github.com/caleb695/AI-agent-skill/tree/main/.agents/skills/relentless`
- Claude Code: copy the directory to `.claude/skills/relentless/` (project) or `~/.claude/skills/relentless/` (personal).

## Verify changes

```sh
python3 -m unittest discover -s .agents/skills/relentless/tests -v
```
