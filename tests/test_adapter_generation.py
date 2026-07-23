import importlib.util
import json
import shutil
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


def write_fixture_repository(root: Path, invalid_second_skill: bool = False):
    for skill_id in ("one-skill", "two-skill"):
        skill = root / "skills" / skill_id
        (skill / "references").mkdir(parents=True)
        (skill / "references" / "guide.md").write_text("# Guide\n")
        reference = (
            "references/missing.md"
            if invalid_second_skill and skill_id == "two-skill"
            else "references/guide.md"
        )
        (skill / "SKILL.md").write_text(
            f"---\nname: {skill_id}\ndescription: Fixture skill.\n---\n\n"
            f"Read `{reference}`.\n"
        )
        (root / "plugins" / skill_id).mkdir(parents=True)

    catalog = {
        "schema_version": 1,
        "plugins": [
            {
                "id": skill_id,
                "package": f"plugins/{skill_id}",
                "capability": {
                    "kind": "skill",
                    "canonical_path": f"skills/{skill_id}/SKILL.md",
                    "package_path": f"skills/{skill_id}/SKILL.md",
                    "legacy_package_path": "skills/SKILL.md",
                },
            }
            for skill_id in ("one-skill", "two-skill")
        ],
    }
    (root / "plugins" / "catalog.json").write_text(json.dumps(catalog))


class AdapterGenerationTests(unittest.TestCase):
    def test_materializes_complete_skill_units_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fixture_repository(root)

            first_changes = generator.generate_adapters(root)
            second_changes = generator.generate_adapters(root)

            self.assertEqual(
                first_changes,
                [
                    "plugins/one-skill/skills/one-skill",
                    "plugins/two-skill/skills/two-skill",
                ],
            )
            self.assertEqual(second_changes, [])
            self.assertEqual(
                (root / "plugins/one-skill/skills/one-skill/references/guide.md").read_text(),
                "# Guide\n",
            )

    def test_check_mode_reports_drift_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fixture_repository(root)

            changes = generator.generate_adapters(root, check=True)

            self.assertEqual(len(changes), 2)
            self.assertFalse((root / "plugins/one-skill/skills/one-skill").exists())

    def test_invalid_input_does_not_partially_replace_outputs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fixture_repository(root, invalid_second_skill=True)
            existing = root / "plugins/one-skill/skills/one-skill"
            existing.mkdir(parents=True)
            (existing / "preserved.txt").write_text("keep")

            with self.assertRaises(generator.GenerationFailure):
                generator.generate_adapters(root)

            self.assertEqual((existing / "preserved.txt").read_text(), "keep")
            self.assertFalse((root / "plugins/two-skill/skills/two-skill").exists())

    def test_real_packages_are_self_contained_and_have_no_legacy_duplicate(self):
        catalog = json.loads((ROOT / "plugins" / "catalog.json").read_text())
        ordinary_skills = [
            plugin for plugin in catalog["plugins"] if plugin["capability"]["kind"] == "skill"
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory)
            for plugin in ordinary_skills:
                package = ROOT / plugin["package"]
                isolated = destination / plugin["id"]
                shutil.copytree(package, isolated)
                skill = isolated / Path(plugin["capability"]["package_path"]).parent

                self.assertEqual(generator.validate_skill(skill), [])
                self.assertFalse((isolated / "skills" / "SKILL.md").exists())

    def test_cursor_manifests_reference_generated_package_local_skills(self):
        catalog = json.loads((ROOT / "plugins" / "catalog.json").read_text())

        for plugin in catalog["plugins"]:
            with self.subTest(plugin=plugin["id"]):
                package = ROOT / plugin["package"]
                manifest = json.loads(
                    (package / ".cursor-plugin" / "plugin.json").read_text()
                )
                skill_root = package / manifest["skills"]
                skill = skill_root / plugin["id"]

                self.assertTrue(skill.is_dir())
                self.assertFalse(skill.is_symlink())
                self.assertEqual(generator.validate_skill(skill), [])
                canonical = ROOT / Path(plugin["capability"]["canonical_path"]).parent
                self.assertEqual(generator._tree_files(skill), generator._tree_files(canonical))


if __name__ == "__main__":
    unittest.main()
