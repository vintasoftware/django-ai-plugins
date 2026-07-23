import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_script("generate_adapters")
smoke = load_script("smoke_plugins")


class NativeDistributionTests(unittest.TestCase):
    def load_catalog(self):
        return json.loads((ROOT / "plugins" / "catalog.json").read_text())

    def test_marketplaces_have_the_same_five_stable_ids(self):
        expected = [plugin["id"] for plugin in self.load_catalog()["plugins"]]
        claude = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        codex = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
        cursor = json.loads((ROOT / ".cursor-plugin" / "marketplace.json").read_text())

        self.assertEqual([plugin["name"] for plugin in claude["plugins"]], expected)
        self.assertEqual([plugin["name"] for plugin in codex["plugins"]], expected)
        self.assertEqual([plugin["name"] for plugin in cursor["plugins"]], expected)

    def test_native_manifests_match_catalog_and_expose_one_host_surface(self):
        for plugin in self.load_catalog()["plugins"]:
            package = ROOT / plugin["package"]
            for target in ("claude", "codex", "cursor"):
                with self.subTest(plugin=plugin["id"], target=target):
                    manifest = json.loads(
                        (
                            package
                            / f".{target}-plugin"
                            / "plugin.json"
                        ).read_text()
                    )
                    self.assertEqual(manifest["name"], plugin["id"])
                    self.assertEqual(manifest["version"], plugin["version"])
                    self.assertEqual(manifest["description"], plugin["description"])
                    capabilities = smoke.discover_capabilities(package, target)
                    self.assertEqual(len(capabilities), 1)
                    self.assertTrue(capabilities[0]["path"].is_file())

    def test_isolated_smoke_never_uses_real_user_homes(self):
        for target in ("claude", "codex", "cursor", "opencode", "agent-skills"):
            with self.subTest(target=target):
                results = smoke.smoke_repository(ROOT, target)

                self.assertEqual(len(results), 5)
                self.assertTrue(all(result["status"] == "ok" for result in results))
                self.assertTrue(
                    all(str(result["installed_root"]).startswith("/tmp/") for result in results)
                )

    def test_install_update_and_uninstall_preserve_other_plugins(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            first = smoke.install_package(ROOT, home, "django-expert")
            second = smoke.install_package(ROOT, home, "cdrf-expert")
            marker = first / "local-marker"
            marker.write_text("stale")

            updated = smoke.install_package(ROOT, home, "django-expert")

            self.assertFalse((updated / "local-marker").exists())
            self.assertTrue(second.is_dir())
            smoke.uninstall_package(home, "django-expert")
            self.assertFalse(updated.exists())
            self.assertTrue(second.is_dir())
            self.assertTrue((ROOT / "plugins" / "django-expert").is_dir())

    def test_duplicate_detection_reports_provenance_and_remediation(self):
        duplicates = smoke.find_duplicates(
            [
                ("django-expert", "codex-marketplace"),
                ("django-expert", "direct-agent-skill"),
                ("cdrf-expert", "codex-marketplace"),
            ]
        )

        self.assertEqual(
            duplicates,
            {
                "django-expert": {
                    "provenance": ["codex-marketplace", "direct-agent-skill"],
                    "remediation": "keep one installation channel and remove the shadow copy",
                }
            },
        )

    def test_layout_versions_are_bumped_for_cache_refresh(self):
        versions = {plugin["version"] for plugin in self.load_catalog()["plugins"]}

        self.assertEqual(versions, {"1.1.0"})

    def test_catalog_change_marks_every_native_output_stale(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "plugins").mkdir()
            shutil.copytree(ROOT / "skills" / "cdrf-expert", root / "skills/cdrf-expert")
            (root / "plugins/cdrf-expert").mkdir()
            source_catalog = self.load_catalog()
            catalog = {
                **{
                    key: source_catalog[key]
                    for key in (
                        "schema_version",
                        "repository",
                        "defaults",
                        "marketplaces",
                    )
                },
                "plugins": [
                    next(
                        plugin
                        for plugin in source_catalog["plugins"]
                        if plugin["id"] == "cdrf-expert"
                    )
                ],
            }
            (root / "plugins/catalog.json").write_text(json.dumps(catalog))

            generator.generate_adapters(root)
            catalog["plugins"][0]["description"] = "Updated fixture description."
            (root / "plugins/catalog.json").write_text(json.dumps(catalog))

            stale = generator.generate_adapters(root, check=True)

            self.assertIn(".claude-plugin/marketplace.json", stale)
            self.assertIn(
                "plugins/cdrf-expert/.claude-plugin/plugin.json",
                stale,
            )
            self.assertIn(
                "plugins/cdrf-expert/.codex-plugin/plugin.json",
                stale,
            )
            self.assertIn(
                "plugins/cdrf-expert/.cursor-plugin/plugin.json",
                stale,
            )
            generator.generate_adapters(root)
            self.assertEqual(generator.generate_adapters(root, check=True), [])

    def test_opencode_adapter_registers_only_the_canonical_skills_path(self):
        results = smoke.smoke_repository(ROOT, "opencode")

        self.assertEqual(len(results), 5)
        self.assertTrue(all(result["provenance"] == "opencode-plugin" for result in results))

    def test_repository_package_is_private_dependency_free_esm(self):
        package = json.loads((ROOT / "package.json").read_text())

        self.assertTrue(package["private"])
        self.assertEqual(package["type"], "module")
        self.assertNotIn("dependencies", package)
        self.assertNotIn("devDependencies", package)
        self.assertNotIn("scripts", package)

    def test_generic_agent_skills_are_the_five_canonical_directories(self):
        expected = [plugin["id"] for plugin in self.load_catalog()["plugins"]]
        discovered = sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))

        self.assertEqual(discovered, sorted(expected))
        for skill_id in discovered:
            self.assertEqual(generator.validate_skill(ROOT / "skills" / skill_id), [])


if __name__ == "__main__":
    unittest.main()
