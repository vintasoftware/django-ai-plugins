import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "scripts" / "generate_adapters.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_adapters", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_generator()


def fixture_plugin(skill_id: str) -> dict:
    return {
        "id": skill_id,
        "version": "1.0.0",
        "description": f"{skill_id} fixture skill.",
        "package": f"plugins/{skill_id}",
        "capability": {
            "kind": "skill",
            "canonical_path": f"skills/{skill_id}/SKILL.md",
            "package_path": f"skills/{skill_id}/SKILL.md",
            "legacy_package_path": "skills/SKILL.md",
        },
        "hosts": ["claude", "codex", "cursor", "opencode", "agent-skills"],
        "keywords": ["fixture"],
        "interface": {
            "display_name": skill_id.replace("-", " ").title(),
            "short_description": "Fixture skill.",
            "long_description": "Fixture skill used by adapter generation tests.",
            "default_prompts": ["Use the fixture skill."],
        },
    }


def fixture_catalog() -> dict:
    return {
        "schema_version": 1,
        "repository": "https://example.test/django-ai-skills",
        "defaults": {
            "author": {"name": "Fixture Author", "url": "https://example.test"},
            "homepage": "https://example.test/django-ai-skills",
            "license": "MIT",
            "category": "Developer Tools",
        },
        "marketplaces": {
            "claude": {"name": "fixtures", "display_name": "Fixtures"},
            "codex": {"name": "fixtures", "display_name": "Fixtures"},
            "cursor": {"name": "fixtures", "display_name": "Fixtures"},
        },
        "plugins": [
            fixture_plugin("one-skill"),
            fixture_plugin("two-skill"),
        ],
    }


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

    write_catalog(root, fixture_catalog())


def write_catalog(root: Path, catalog: dict) -> None:
    (root / "plugins").mkdir(parents=True, exist_ok=True)
    (root / "plugins" / "catalog.json").write_text(json.dumps(catalog))


class AdapterGenerationTests(unittest.TestCase):
    def test_materializes_complete_skill_units_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fixture_repository(root)

            first_changes = generator.generate_adapters(root)
            second_changes = generator.generate_adapters(root)

            self.assertIn("plugins/one-skill/skills/one-skill", first_changes)
            self.assertIn("plugins/two-skill/skills/two-skill", first_changes)
            self.assertIn(".claude-plugin/marketplace.json", first_changes)
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

            self.assertIn("plugins/one-skill/skills/one-skill", changes)
            self.assertIn("plugins/two-skill/skills/two-skill", changes)
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

    def test_catalog_paths_cannot_escape_boundaries(self):
        mutations = {
            "package": ("package", "../outside-package"),
            "canonical_path": ("canonical_path", "../outside/SKILL.md"),
            "package_path": ("package_path", "../outside/SKILL.md"),
            "legacy_package_path": (
                "legacy_package_path",
                "../outside/legacy.md",
            ),
            "agent_path": ("agent_path", "../outside-agent.md"),
        }
        for label, (field, unsafe_value) in mutations.items():
            with self.subTest(path=label), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                root = base / "repo"
                root.mkdir()
                write_fixture_repository(root)
                outside = base / "outside"
                outside.mkdir()
                sentinel = outside / "sentinel.txt"
                sentinel.write_text("preserve")
                catalog = json.loads((root / "plugins/catalog.json").read_text())
                plugin = catalog["plugins"][0]
                if field == "package":
                    plugin["package"] = unsafe_value
                elif field == "agent_path":
                    plugin["capability"]["kind"] = "hybrid"
                    plugin["overrides"] = {
                        "claude": {
                            "agent_path": unsafe_value,
                            "model": "opus",
                            "description": "Fixture reviewer.",
                        }
                    }
                else:
                    plugin["capability"][field] = unsafe_value
                write_catalog(root, catalog)
                before = generator._tree_files(base)

                with self.assertRaisesRegex(
                    generator.GenerationFailure, label.replace("_", ".*")
                ):
                    generator.generate_adapters(root)

                self.assertEqual(generator._tree_files(base), before)
                self.assertEqual(sentinel.read_text(), "preserve")

    def test_symlinked_catalog_ancestor_is_rejected_without_reading_outside(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            root.mkdir()
            write_fixture_repository(root)
            outside = base / "outside"
            outside.mkdir()
            (outside / "SKILL.md").write_text(
                "---\nname: one-skill\ndescription: Outside.\n---\n"
            )
            linked = root / "linked-skill"
            linked.symlink_to(outside, target_is_directory=True)
            catalog = json.loads((root / "plugins/catalog.json").read_text())
            catalog["plugins"][0]["capability"][
                "canonical_path"
            ] = "linked-skill/SKILL.md"
            write_catalog(root, catalog)
            before = generator._tree_files(base)

            with self.assertRaisesRegex(
                generator.GenerationFailure, "symlinked.*linked-skill"
            ):
                generator.generate_adapters(root)

            self.assertEqual(generator._tree_files(base), before)

    def test_frontmatter_rejects_quoted_and_nonportable_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "sample-skill"
            skill.mkdir()
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                '---\nname: sample-skill\n"description": Safe.\n---\n'
            )
            self.assertTrue(
                any(
                    "invalid frontmatter key syntax" in error
                    for error in generator.validate_skill(skill)
                )
            )

            skill_file.write_text(
                "---\nname: sample-skill\ndescription: Safe.\nmodel: opus\n---\n"
            )
            self.assertTrue(
                any(
                    "non-portable frontmatter field 'model'" in error
                    for error in generator.validate_skill(skill)
                )
            )

    def test_claude_override_is_validated_and_unsafe_yaml_scalars_are_quoted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture_repository(root)
            catalog = json.loads((root / "plugins/catalog.json").read_text())
            reviewer = catalog["plugins"][0]
            reviewer["capability"]["kind"] = "hybrid"
            reviewer["capability"][
                "package_path"
            ] = "portable-skills/one-skill/SKILL.md"
            reviewer["overrides"] = {
                "claude": {
                    "agent_path": "agents/one-skill.md",
                    "model": "opus",
                    "description": "Safe line\nmodel: injected",
                }
            }
            write_catalog(root, catalog)

            generator.generate_adapters(root)

            agent = (root / "plugins/one-skill/agents/one-skill.md").read_text()
            frontmatter = agent.split("---", 2)[1]
            self.assertIn("name: one-skill", frontmatter)
            self.assertIn('description: "Safe line\\nmodel: injected"', frontmatter)
            self.assertEqual(frontmatter.count("\nmodel:"), 1)

            reviewer["overrides"]["claude"]["model"] = "opus\npermission: allow"
            write_catalog(root, catalog)
            with self.assertRaisesRegex(
                generator.GenerationFailure, "invalid Claude model"
            ):
                generator.generate_adapters(root)

            reviewer["overrides"]["claude"]["model"] = "opus"
            reviewer["overrides"]["claude"]["unexpected"] = True
            write_catalog(root, catalog)
            with self.assertRaisesRegex(
                generator.GenerationFailure, "unsupported Claude override"
            ):
                generator.generate_adapters(root)

    def test_missing_required_catalog_sections_fail_closed(self):
        for field in (
            "repository",
            "defaults",
            "marketplaces",
            "plugins",
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                write_fixture_repository(root)
                catalog = json.loads((root / "plugins/catalog.json").read_text())
                del catalog[field]
                write_catalog(root, catalog)
                before = generator._tree_files(root)

                with self.assertRaisesRegex(
                    generator.GenerationFailure, f"catalog.*{field}"
                ):
                    generator.generate_adapters(root)

                self.assertEqual(generator._tree_files(root), before)

    def test_generation_rolls_back_every_mutation_on_late_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture_repository(root)
            legacy = root / "plugins/one-skill/skills"
            (legacy / "references").mkdir(parents=True)
            (legacy / "SKILL.md").write_text("legacy skill\n")
            (legacy / "references/legacy.md").write_text("legacy reference\n")
            orphan = root / "plugins/orphan/.claude-plugin/plugin.json"
            orphan.parent.mkdir(parents=True)
            orphan.write_text(json.dumps({"name": "orphan"}))
            before = generator._tree_files(root)
            original_replace_file = generator._replace_file
            calls = 0

            def fail_on_second_file(content, target):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected late write failure")
                original_replace_file(content, target)

            with mock.patch.object(
                generator, "_replace_file", side_effect=fail_on_second_file
            ):
                with self.assertRaisesRegex(
                    generator.GenerationFailure, "injected late write failure"
                ):
                    generator.generate_adapters(root)

            self.assertEqual(generator._tree_files(root), before)

    def test_flat_legacy_tree_is_normalized_without_touching_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture_repository(root)
            package = root / "plugins/one-skill"
            flat = package / "skills"
            (flat / "references").mkdir(parents=True)
            (flat / "SKILL.md").write_text("legacy flat skill\n")
            (flat / "references/legacy.md").write_text("legacy reference\n")
            (package / "README.md").write_text("keep package docs\n")

            generator.generate_adapters(root)

            nested = package / "skills/one-skill"
            canonical = root / "skills/one-skill"
            self.assertEqual(
                generator._tree_files(nested),
                generator._tree_files(canonical),
            )
            self.assertFalse((flat / "SKILL.md").exists())
            self.assertFalse((flat / "references").exists())
            self.assertEqual(
                (package / "README.md").read_text(),
                "keep package docs\n",
            )

    def test_hosts_gate_and_prune_native_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture_repository(root)
            generator.generate_adapters(root)
            catalog = json.loads((root / "plugins/catalog.json").read_text())
            catalog["plugins"][0]["hosts"] = [
                "claude",
                "opencode",
                "agent-skills",
            ]
            catalog["plugins"][1]["hosts"] = ["opencode", "agent-skills"]
            write_catalog(root, catalog)

            generator.generate_adapters(root)

            first = root / "plugins/one-skill"
            second = root / "plugins/two-skill"
            self.assertTrue((first / ".claude-plugin/plugin.json").is_file())
            self.assertFalse((first / ".codex-plugin/plugin.json").exists())
            self.assertFalse((first / ".cursor-plugin/plugin.json").exists())
            self.assertTrue((first / "skills/one-skill/SKILL.md").is_file())
            self.assertFalse((second / ".claude-plugin/plugin.json").exists())
            self.assertFalse((second / ".codex-plugin/plugin.json").exists())
            self.assertFalse((second / ".cursor-plugin/plugin.json").exists())
            self.assertFalse((second / "skills/two-skill").exists())
            claude = json.loads(
                (root / ".claude-plugin/marketplace.json").read_text()
            )
            codex = json.loads(
                (root / ".agents/plugins/marketplace.json").read_text()
            )
            cursor = json.loads(
                (root / ".cursor-plugin/marketplace.json").read_text()
            )
            self.assertEqual(
                [plugin["name"] for plugin in claude["plugins"]],
                ["one-skill"],
            )
            self.assertEqual(codex["plugins"], [])
            self.assertEqual(cursor["plugins"], [])

    def test_removed_package_cleanup_uses_manifest_id_not_directory_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture_repository(root)
            catalog = json.loads((root / "plugins/catalog.json").read_text())
            plugin = catalog["plugins"][0]
            old_package = root / plugin["package"]
            renamed_package = root / "plugins/one-skill-bundle"
            old_package.rename(renamed_package)
            plugin["package"] = "plugins/one-skill-bundle"
            write_catalog(root, catalog)
            generator.generate_adapters(root)

            catalog["plugins"] = catalog["plugins"][1:]
            write_catalog(root, catalog)
            changes = generator.generate_adapters(root)

            self.assertIn(
                "plugins/one-skill-bundle/.claude-plugin/plugin.json",
                changes,
            )
            self.assertFalse(
                (renamed_package / ".claude-plugin/plugin.json").exists()
            )
            self.assertFalse(
                (renamed_package / "skills/one-skill").exists()
            )

    def test_malformed_orphan_manifest_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture_repository(root)
            orphan = root / "plugins/orphan/.claude-plugin/plugin.json"
            orphan.parent.mkdir(parents=True)
            orphan.write_text("{")
            before = generator._tree_files(root)

            with self.assertRaisesRegex(
                generator.GenerationFailure,
                r"plugins/orphan/\.claude-plugin/plugin\.json.*invalid JSON",
            ):
                generator.generate_adapters(root)

            self.assertEqual(generator._tree_files(root), before)

    def test_markdown_links_validate_filenames_fragments_and_queries(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "sample-skill"
            skill.mkdir()
            (skill / "guide.md").write_text("# Guide\n")
            (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Fixture.\n---\n\n"
                "[Guide](guide.md?raw=1#section)\n"
                "[Missing](missing.md#section)\n"
                "[Anchor](#local)\n"
                "[External](https://example.test/remote.md)\n"
                "`not-a-reference.md`\n"
            )

            errors = generator.validate_skill(skill)

            self.assertEqual(len(errors), 1)
            self.assertTrue(any("missing.md" in error for error in errors))

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
