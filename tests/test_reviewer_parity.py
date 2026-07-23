import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skills" / "django-reviewer" / "SKILL.md"
AGENT = ROOT / "plugins" / "django-reviewer" / "agents" / "django-reviewer.md"
PORTABLE = (
    ROOT
    / "plugins"
    / "django-reviewer"
    / "portable-skills"
    / "django-reviewer"
)
GENERATOR_PATH = ROOT / "scripts" / "generate_adapters.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_adapters", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_generator()


class ReviewerParityTests(unittest.TestCase):
    def test_canonical_skill_and_claude_agent_share_review_contract(self):
        canonical = CANONICAL.read_text()
        agent = AGENT.read_text()

        for contract in (
            "Preserve Functionality",
            "Apply Project Standards",
            "Focus Scope",
            "recently modified",
            "select_related",
            "without changing behavior",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, canonical)
                self.assertIn(contract, agent)

    def test_portable_skill_is_permission_bounded_and_host_neutral(self):
        content = CANONICAL.read_text()
        frontmatter = content.split("---", 2)[1]

        self.assertNotIn("model:", frontmatter)
        self.assertNotIn("proactive", content.lower())
        self.assertNotIn("autonomous", content.lower())
        self.assertNotIn("CLAUDE.md", content)
        self.assertIn("explicit edit intent", content)
        self.assertIn("report-only", content)
        self.assertIn("project instruction files", content)

    def test_target_resolution_is_bounded(self):
        content = CANONICAL.read_text()

        self.assertIn("explicitly named files", content)
        self.assertIn("git diff", content)
        self.assertIn("no changed files", content)
        self.assertIn("ask for a target", content)
        self.assertIn("Do not broaden", content)

    def test_generated_agent_keeps_claude_metadata_outside_canonical_skill(self):
        canonical_frontmatter = CANONICAL.read_text().split("---", 2)[1]
        agent_frontmatter = AGENT.read_text().split("---", 2)[1]

        self.assertNotIn("model:", canonical_frontmatter)
        self.assertIn("model: opus", agent_frontmatter)
        self.assertIn("Use proactively after Django code changes.", agent_frontmatter)

    def test_portable_projection_is_self_contained(self):
        self.assertEqual(generator.validate_skill(PORTABLE), [])
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated = Path(temporary_directory) / "django-reviewer"
            shutil.copytree(ROOT / "plugins" / "django-reviewer", isolated)

            self.assertEqual(
                generator.validate_skill(
                    isolated / "portable-skills" / "django-reviewer"
                ),
                [],
            )


if __name__ == "__main__":
    unittest.main()
