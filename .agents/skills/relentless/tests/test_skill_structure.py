from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")


class SkillStructureTest(unittest.TestCase):
    def test_frontmatter_identity_and_compatibility(self) -> None:
        match = re.match(r"\A---\n(.*?)\n---\n", SKILL, re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1)
        self.assertRegex(frontmatter, r"(?m)^name: relentless$")
        self.assertRegex(frontmatter, r"(?m)^description: .{80,}")
        self.assertIn("Python 3.10+", frontmatter)

    def test_stop_hook_is_registered_to_existing_bundled_script(self) -> None:
        self.assertRegex(SKILL, r"(?m)^hooks:\n  Stop:\n")
        self.assertIn('command: "python3"', SKILL)
        self.assertIn('"${CLAUDE_SKILL_DIR}/scripts/stop_hook.py"', SKILL)
        self.assertTrue((ROOT / "scripts" / "stop_hook.py").is_file())
        self.assertTrue((ROOT / "scripts" / "relentless.py").is_file())

    def test_skill_requires_executable_workflow(self) -> None:
        for command in (
            "init",
            "requirement-add",
            "attempt-start",
            "attempt-end",
            "review",
            "requirement-verify",
            "requirement-unverify",
            "status",
            "complete",
            "stop",
            "resume",
        ):
            self.assertIn(command, SKILL)
        self.assertIn("Do not substitute a mental checklist", SKILL)
        self.assertIn("--check-command", SKILL)

    def test_skill_lives_in_standard_agents_directory(self) -> None:
        skill_dir = Path(__file__).resolve().parents[1]
        repo_root = Path(__file__).resolve().parents[4]
        expected = repo_root / ".agents" / "skills" / "relentless" / "SKILL.md"
        self.assertEqual(expected, skill_dir / "SKILL.md")
        self.assertTrue(expected.is_file())
        self.assertEqual(expected.parent.name, "relentless")
        # OpenHands keyword activation and loader-friendly frontmatter.
        self.assertRegex(SKILL, r"(?m)^triggers:\n  - relentless\n")
        self.assertRegex(SKILL, r"(?m)^compatibility: ")

    def test_numbered_protocol_sections_are_ordered(self) -> None:
        sections = [int(value) for value in re.findall(r"^## (\d+)\.", SKILL, re.MULTILINE)]
        self.assertEqual(sections, list(range(1, 8)))


class OpenHandsMarketplaceTest(unittest.TestCase):
    """The repository must resolve as an OpenHands Cloud plugin marketplace."""

    ROOT = Path(__file__).resolve().parents[1]
    REPO = Path(__file__).resolve().parents[4]

    def marketplace(self) -> dict:
        manifest = self.REPO / ".plugin" / "marketplace.json"
        self.assertTrue(manifest.is_file(), manifest)
        return json.loads(manifest.read_text(encoding="utf-8"))

    def test_manifest_declares_relentless_plugin(self) -> None:
        manifest = self.marketplace()
        self.assertTrue(manifest.get("name"))
        self.assertTrue(manifest.get("owner", {}).get("name"))
        plugin = next(
            (p for p in manifest.get("plugins", []) if p.get("name") == "relentless"),
            None,
        )
        self.assertIsNotNone(plugin, "marketplace must declare the relentless plugin")
        self.assertEqual(plugin["source"], "./skills/relentless")

    def test_marketplace_source_resolves_to_the_skill(self) -> None:
        # Mirrors Marketplace.resolve_plugin_source: "./skills/relentless" ->
        # <repo>/skills/relentless, which the symlink resolves to
        # .agents/skills/relentless.
        resolved = (self.REPO / "./skills/relentless".lstrip("./")).resolve()
        self.assertTrue(resolved.is_dir(), resolved)
        self.assertTrue((resolved / "SKILL.md").is_file())
        self.assertTrue((resolved / ".plugin" / "plugin.json").is_file())

    def test_skills_symlink_exposes_standard_marketplace_path(self) -> None:
        # OpenHands also accepts a plain skills/<name>/SKILL.md repository; the
        # symlink makes that path available without duplicating the skill.
        skills = self.REPO / "skills"
        self.assertTrue(skills.is_symlink() or skills.is_dir(), skills)
        self.assertTrue((skills / "relentless" / "SKILL.md").is_file())

    def test_plugin_manifest_name_matches_skill(self) -> None:
        plugin_manifest = json.loads(
            (self.ROOT / ".plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        skill_name = re.search(r"(?m)^name:\s*(.+?)\s*$", SKILL)
        self.assertIsNotNone(skill_name)
        self.assertEqual(plugin_manifest["name"], skill_name.group(1))

    def test_vendor_plugin_symlinks_point_at_plugin_dir(self) -> None:
        for link in (".claude-plugin", ".codex-plugin"):
            path = self.ROOT / link
            self.assertTrue(path.is_symlink(), link)
            self.assertEqual(os.readlink(path), ".plugin")


if __name__ == "__main__":
    unittest.main()
