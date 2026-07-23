#!/usr/bin/env python3
"""Run isolated structural smoke checks for generated plugin packages."""

from __future__ import annotations

import argparse
import json
import shutil
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
    elif target == "codex":
        skill_root_value = manifest.get("skills")
        if not isinstance(skill_root_value, str):
            raise SmokeFailure(f"{package}: Codex manifest has no skills path")
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


def smoke_repository(root: Path, target: str) -> list[dict[str, Any]]:
    catalog = _load_catalog(root)
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"django-ai-{target}-", dir="/tmp") as temporary:
        home = Path(temporary)
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
    parser.add_argument("--target", choices=("claude", "codex"), required=True)
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
