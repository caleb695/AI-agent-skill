from __future__ import annotations

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

    def test_numbered_protocol_sections_are_ordered(self) -> None:
        sections = [int(value) for value in re.findall(r"^## (\d+)\.", SKILL, re.MULTILINE)]
        self.assertEqual(sections, list(range(1, 8)))


if __name__ == "__main__":
    unittest.main()
