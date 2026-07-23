import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "scripts" / "generate_adapters.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_adapters", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_generator()


class SkillContractTests(unittest.TestCase):
    def test_canonical_skills_match_directory_and_resolve_references(self):
        for skill_id in (
            "django-expert",
            "django-celery-expert",
            "cdrf-expert",
            "django-safe-migration",
        ):
            with self.subTest(skill=skill_id):
                errors = generator.validate_skill(ROOT / "skills" / skill_id)
                self.assertEqual(errors, [])

    def test_invalid_frontmatter_and_escaping_references_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            skill = Path(temporary_directory) / "expected-name"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\n"
                "name: wrong-name\n"
                "description: Test skill.\n"
                "model: opus\n"
                "---\n\n"
                "# Test\n\n"
                "Read `../outside.md` and `/tmp/absolute.md`.\n"
            )

            errors = generator.validate_skill(skill)

            self.assertTrue(any("must match directory" in error for error in errors))
            self.assertTrue(any("host-only frontmatter 'model'" in error for error in errors))
            self.assertTrue(any("escapes the skill directory" in error for error in errors))
            self.assertTrue(any("absolute reference" in error for error in errors))

    def test_missing_and_case_mismatched_references_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            skill = Path(temporary_directory) / "sample-skill"
            (skill / "references").mkdir(parents=True)
            (skill / "references" / "Guide.md").write_text("# Guide\n")
            (skill / "SKILL.md").write_text(
                "---\n"
                "name: sample-skill\n"
                "description: Test skill.\n"
                "---\n\n"
                "Read `references/guide.md` and `references/missing.md`.\n"
            )

            errors = generator.validate_skill(skill)

            self.assertTrue(any("case mismatch" in error for error in errors))
            self.assertTrue(any("missing reference" in error for error in errors))

    def test_symlinks_are_rejected_before_materialization(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            skill = Path(temporary_directory) / "sample-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n"
            )
            outside = Path(temporary_directory) / "outside.md"
            outside.write_text("secret")
            (skill / "linked.md").symlink_to(outside)

            errors = generator.validate_skill(skill)

            self.assertTrue(any("symlink" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
