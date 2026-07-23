#!/usr/bin/env python3
"""Run isolated structural smoke checks for generated plugin packages."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]


class SmokeFailure(RuntimeError):
    """Raised when an installed package does not expose its declared surface."""


def _load_catalog(root: Path) -> dict[str, Any]:
    return json.loads((root / "plugins" / "catalog.json").read_text())


def _manifest(package: Path, target: str) -> dict[str, Any]:
    path = package / f".{target}-plugin" / "plugin.json"
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise SmokeFailure(f"{path}: invalid or missing manifest") from error


def discover_capabilities(package: Path, target: str) -> list[dict[str, Any]]:
    manifest = _manifest(package, target)
    capabilities: list[dict[str, Any]] = []
    if target == "claude":
        for path in sorted((package / "agents").glob("*.md")):
            capabilities.append(
                {"id": path.stem, "kind": "agent", "path": path, "target": target}
            )
        for path in sorted((package / "skills").glob("*/SKILL.md")):
            capabilities.append(
                {
                    "id": path.parent.name,
                    "kind": "skill",
                    "path": path,
                    "target": target,
                }
            )
    elif target in {"codex", "cursor"}:
        skill_root_value = manifest.get("skills")
        if not isinstance(skill_root_value, str):
            raise SmokeFailure(f"{package}: {target} manifest has no skills path")
        skill_root = package / skill_root_value
        for path in sorted(skill_root.glob("*/SKILL.md")):
            capabilities.append(
                {
                    "id": path.parent.name,
                    "kind": "skill",
                    "path": path,
                    "target": target,
                }
            )
    else:
        raise SmokeFailure(f"unsupported smoke target '{target}'")

    if len(capabilities) != 1:
        raise SmokeFailure(
            f"{package}: expected one {target} capability, found {len(capabilities)}"
        )
    if capabilities[0]["id"] != manifest["name"]:
        raise SmokeFailure(
            f"{package}: capability '{capabilities[0]['id']}' does not match "
            f"manifest '{manifest['name']}'"
        )
    return capabilities


def install_package(root: Path, home: Path, plugin_id: str) -> Path:
    source = root / "plugins" / plugin_id
    if not source.is_dir():
        raise SmokeFailure(f"unknown plugin '{plugin_id}'")
    plugins_home = home / "plugins"
    plugins_home.mkdir(parents=True, exist_ok=True)
    destination = plugins_home / plugin_id
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


def uninstall_package(home: Path, plugin_id: str) -> None:
    destination = home / "plugins" / plugin_id
    if destination.exists():
        shutil.rmtree(destination)


def find_duplicates(
    registrations: Iterable[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    provenance: dict[str, list[str]] = defaultdict(list)
    for plugin_id, source in registrations:
        provenance[plugin_id].append(source)
    return {
        plugin_id: {
            "provenance": sources,
            "remediation": "keep one installation channel and remove the shadow copy",
        }
        for plugin_id, sources in provenance.items()
        if len(sources) > 1
    }


def _smoke_opencode(
    root: Path, home: Path, catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    checkout = home / "checkout"
    shutil.copytree(root / ".opencode", checkout / ".opencode")
    shutil.copytree(root / "skills", checkout / "skills")
    shutil.copy2(root / "package.json", checkout / "package.json")
    adapter = checkout / ".opencode" / "plugins" / "django-ai-skills.js"
    script = (
        f"import plugin from {json.dumps(adapter.as_uri())};"
        "const hooks = await plugin();"
        "const config = {};"
        "await hooks.config(config);"
        "await hooks.config(config);"
        "process.stdout.write(JSON.stringify({"
        "hooks: Object.keys(hooks), paths: config.skills.paths"
        "}));"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise SmokeFailure(
            f"OpenCode adapter failed to load: {completed.stderr.strip()}"
        )
    loaded = json.loads(completed.stdout)
    paths = loaded.get("paths", [])
    registered_path = Path(paths[0]).resolve() if len(paths) == 1 else None
    if (
        loaded.get("hooks") != ["config"]
        or registered_path != (checkout / "skills").resolve()
    ):
        raise SmokeFailure(
            "OpenCode adapter must register only the copied canonical skills path"
        )
    return [
        {
            "plugin": plugin["id"],
            "status": "ok",
            "installed_root": checkout,
            "capability": plugin["id"],
            "provenance": "opencode-plugin",
        }
        for plugin in catalog["plugins"]
    ]


def _smoke_agent_skills(
    root: Path, home: Path, catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    skills_home = home / "skills"
    shutil.copytree(root / "skills", skills_home)
    expected = sorted(plugin["id"] for plugin in catalog["plugins"])
    discovered = sorted(path.parent.name for path in skills_home.glob("*/SKILL.md"))
    if discovered != expected:
        raise SmokeFailure(
            f"generic Agent Skills IDs differ: expected {expected}, found {discovered}"
        )
    return [
        {
            "plugin": plugin_id,
            "status": "ok",
            "installed_root": skills_home,
            "capability": plugin_id,
            "provenance": "direct-agent-skill",
        }
        for plugin_id in discovered
    ]


def smoke_repository(root: Path, target: str) -> list[dict[str, Any]]:
    catalog = _load_catalog(root)
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"django-ai-{target}-", dir="/tmp") as temporary:
        home = Path(temporary)
        if target == "opencode":
            return _smoke_opencode(root, home, catalog)
        if target == "agent-skills":
            return _smoke_agent_skills(root, home, catalog)
        for plugin in catalog["plugins"]:
            installed = install_package(root, home, plugin["id"])
            capabilities = discover_capabilities(installed, target)
            results.append(
                {
                    "plugin": plugin["id"],
                    "status": "ok",
                    "installed_root": installed,
                    "capability": capabilities[0]["id"],
                    "provenance": f"{target}-marketplace",
                }
            )
            uninstall_package(home, plugin["id"])
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=("claude", "codex", "cursor", "opencode", "agent-skills"),
        required=True,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        results = smoke_repository(ROOT, arguments.target)
    except SmokeFailure as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    for result in results:
        print(
            f"OK: {result['plugin']} via {arguments.target} "
            f"({result['capability']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
