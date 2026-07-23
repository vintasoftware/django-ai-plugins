import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationContractTests(unittest.TestCase):
    def load_catalog(self):
        return json.loads((ROOT / "plugins" / "catalog.json").read_text())

    def test_root_readme_links_shared_installation_and_compatibility_docs(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn("docs/installation.md", readme)
        self.assertIn("docs/compatibility.md", readme)
        for plugin in self.load_catalog()["plugins"]:
            self.assertIn(plugin["id"], readme)

    def test_installation_doc_covers_every_host_and_lifecycle_operation(self):
        installation = (ROOT / "docs" / "installation.md").read_text().lower()

        for host in ("claude", "codex", "cursor", "opencode", "agent skills"):
            self.assertIn(host, installation)
        for operation in (
            "install",
            "update",
            "uninstall",
            "cache",
            "duplicate",
            "permission",
        ):
            self.assertIn(operation, installation)

    def test_documented_local_commands_reference_existing_scripts(self):
        installation = (ROOT / "docs" / "installation.md").read_text()
        contributor = (ROOT / "AGENTS.md").read_text()

        for script in (
            "scripts/generate_adapters.py",
            "scripts/validate_plugins.py",
            "scripts/smoke_plugins.py",
        ):
            self.assertIn(script, installation + contributor)
            self.assertTrue((ROOT / script).is_file())

    def test_plugin_readmes_are_capability_focused_and_link_shared_lifecycle(self):
        for plugin in self.load_catalog()["plugins"]:
            with self.subTest(plugin=plugin["id"]):
                readme = (ROOT / plugin["package"] / "README.md").read_text()
                self.assertIn("../../docs/installation.md", readme)
                self.assertNotIn("/plugin marketplace add", readme)
                self.assertNotIn("codex plugin marketplace add", readme)

    def test_ci_runs_every_offline_contract_without_publishing(self):
        workflow = (ROOT / ".github" / "workflows" / "validate-plugins.yml").read_text()

        for command in (
            "python scripts/generate_adapters.py --check",
            "python scripts/validate_plugins.py",
            "python -m unittest discover",
        ):
            self.assertIn(command, workflow)
        for target in ("claude", "codex", "cursor", "opencode", "agent-skills"):
            self.assertIn(f"--target {target}", workflow)
        self.assertNotIn("publish", workflow.lower())
        self.assertNotIn("secrets.", workflow)

    def test_generated_outputs_are_declared_non_editable(self):
        contributor = (ROOT / "AGENTS.md").read_text()

        self.assertIn("Do not edit generated files directly", contributor)
        self.assertIn("plugins/catalog.json", contributor)
        self.assertIn("skills/<id>/", contributor)


if __name__ == "__main__":
    unittest.main()
