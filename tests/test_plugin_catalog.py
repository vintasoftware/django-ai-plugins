import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "plugins" / "catalog.json"
VALIDATOR_PATH = ROOT / "scripts" / "validate_plugins.py"
FIXTURES = ROOT / "tests" / "fixtures" / "catalog"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_plugins", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_validator()


class PluginCatalogTests(unittest.TestCase):
    def load_catalog(self):
        return json.loads(CATALOG_PATH.read_text())

    def test_repository_catalog_contains_the_five_stable_plugins(self):
        catalog = self.load_catalog()

        errors = validator.validate_catalog(catalog, ROOT)

        self.assertEqual(errors, [])
        self.assertEqual(
            [plugin["id"] for plugin in catalog["plugins"]],
            [
                "django-expert",
                "django-celery-expert",
                "cdrf-expert",
                "django-safe-migration",
                "django-reviewer",
            ],
        )

    def test_catalog_rejects_duplicate_ids_and_unknown_roots(self):
        catalog = self.load_catalog()
        duplicate = copy.deepcopy(catalog["plugins"][0])
        duplicate["package"] = "plugins/does-not-exist"
        catalog["plugins"].append(duplicate)

        errors = validator.validate_catalog(catalog, ROOT)

        self.assertTrue(any("duplicate plugin id 'django-expert'" in error for error in errors))
        self.assertTrue(any("plugins/does-not-exist" in error for error in errors))

    def test_catalog_rejects_missing_metadata_invalid_versions_and_kinds(self):
        catalog = self.load_catalog()
        plugin = catalog["plugins"][0]
        del plugin["description"]
        plugin["version"] = "next"
        plugin["capability"]["kind"] = "workflow"

        errors = validator.validate_catalog(catalog, ROOT)

        self.assertTrue(any("description" in error for error in errors))
        self.assertTrue(any("version 'next'" in error for error in errors))
        self.assertTrue(any("capability kind 'workflow'" in error for error in errors))

    def test_catalog_rejects_advertised_plugin_without_executable_surface(self):
        catalog = self.load_catalog()
        plugin = catalog["plugins"][0]
        plugin["capability"]["package_path"] = "skills/missing/SKILL.md"

        errors = validator.validate_catalog(catalog, ROOT)

        self.assertTrue(any("usable surface" in error for error in errors))

    def test_marketplace_validation_reports_missing_extra_and_metadata_drift(self):
        catalog = self.load_catalog()
        marketplace = json.loads(
            (FIXTURES / "marketplaces" / "invalid-claude-marketplace.json").read_text()
        )

        errors = validator.validate_marketplace(catalog, marketplace, "claude")

        self.assertTrue(any("missing plugin 'django-safe-migration'" in error for error in errors))
        self.assertTrue(any("orphan plugin 'orphan-plugin'" in error for error in errors))
        self.assertTrue(any("django-expert" in error and "description" in error for error in errors))

    def test_removing_catalog_record_reports_only_generated_orphans(self):
        catalog = self.load_catalog()
        removed = catalog["plugins"].pop()
        marketplace = {
            "plugins": [
                {
                    "name": plugin["id"],
                    "source": f"./{plugin['package']}",
                    "description": plugin["description"],
                }
                for plugin in catalog["plugins"]
            ]
            + [
                {
                    "name": removed["id"],
                    "source": f"./{removed['package']}",
                    "description": removed["description"],
                }
            ]
        }

        errors = validator.validate_marketplace(catalog, marketplace, "claude")

        self.assertEqual(
            errors,
            [
                "claude marketplace has orphan plugin 'django-reviewer' "
                "(generator-owned record)"
            ],
        )
        self.assertTrue((ROOT / removed["package"]).is_dir())

    def test_load_json_reports_malformed_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "bad.json"
            path.write_text("{")

            with self.assertRaisesRegex(validator.ValidationFailure, "invalid JSON"):
                validator.load_json(path)


if __name__ == "__main__":
    unittest.main()
