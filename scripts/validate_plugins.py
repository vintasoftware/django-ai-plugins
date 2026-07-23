#!/usr/bin/env python3
"""Validate the canonical plugin catalog and generated distribution metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "plugins" / "catalog.json"
MARKETPLACE_PATHS = {
    "claude": ROOT / ".claude-plugin" / "marketplace.json",
    "codex": ROOT / ".agents" / "plugins" / "marketplace.json",
    "cursor": ROOT / ".cursor-plugin" / "marketplace.json",
}
REQUIRED_PLUGIN_FIELDS = {
    "id",
    "version",
    "description",
    "package",
    "capability",
    "hosts",
    "keywords",
    "interface",
}
ALLOWED_CAPABILITY_KINDS = {"skill", "agent", "hybrid"}
ALLOWED_HOSTS = {"claude", "codex", "cursor", "opencode", "agent-skills"}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ValidationFailure(RuntimeError):
    """Raised when an input file cannot be parsed for validation."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as error:
        raise ValidationFailure(f"{path}: file not found") from error
    except json.JSONDecodeError as error:
        raise ValidationFailure(
            f"{path}: invalid JSON at line {error.lineno}, column {error.colno}"
        ) from error
    if not isinstance(value, dict):
        raise ValidationFailure(f"{path}: root value must be an object")
    return value


def _safe_relative_path(value: object) -> PurePosixPath | None:
    if not isinstance(value, str) or not value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        return None
    return path


def _plugin_label(plugin: object, index: int) -> str:
    if isinstance(plugin, dict) and isinstance(plugin.get("id"), str):
        return f"plugin '{plugin['id']}'"
    return f"plugin at index {index}"


def validate_catalog(catalog: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if catalog.get("schema_version") != 1:
        errors.append("catalog schema_version must be 1")

    plugins = catalog.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        return errors + ["catalog plugins must be a non-empty array"]

    seen_ids: set[str] = set()
    for index, plugin in enumerate(plugins):
        label = _plugin_label(plugin, index)
        if not isinstance(plugin, dict):
            errors.append(f"{label} must be an object")
            continue

        missing = sorted(REQUIRED_PLUGIN_FIELDS - plugin.keys())
        for field in missing:
            errors.append(f"{label} is missing required field '{field}'")

        plugin_id = plugin.get("id")
        if not isinstance(plugin_id, str) or not plugin_id:
            errors.append(f"{label} has an invalid id")
        elif plugin_id in seen_ids:
            errors.append(f"duplicate plugin id '{plugin_id}'")
        else:
            seen_ids.add(plugin_id)

        version = plugin.get("version")
        if not isinstance(version, str) or not SEMVER.fullmatch(version):
            errors.append(f"{label} has invalid version '{version}'")

        description = plugin.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{label} has invalid description")

        package_value = plugin.get("package")
        package_relative = _safe_relative_path(package_value)
        package_root: Path | None = None
        package_exists = False
        if package_relative is None:
            errors.append(f"{label} has unsafe package path '{package_value}'")
        else:
            package_root = root.joinpath(*package_relative.parts)
            package_exists = package_root.is_dir()
            if not package_exists:
                errors.append(f"{label} references unknown package root '{package_value}'")

        capability = plugin.get("capability")
        if not isinstance(capability, dict):
            errors.append(f"{label} capability must be an object")
        else:
            kind = capability.get("kind")
            if kind not in ALLOWED_CAPABILITY_KINDS:
                errors.append(f"{label} has unsupported capability kind '{kind}'")
            surface_value = capability.get("package_path")
            surface_relative = _safe_relative_path(surface_value)
            if surface_relative is None:
                errors.append(f"{label} has unsafe capability path '{surface_value}'")
            elif package_root is not None and package_exists:
                surface = package_root.joinpath(*surface_relative.parts)
                if surface.is_symlink() or not surface.is_file():
                    errors.append(
                        f"{label} advertises no usable surface at "
                        f"'{package_value}/{surface_value}'"
                    )

        hosts = plugin.get("hosts")
        if not isinstance(hosts, list) or not hosts:
            errors.append(f"{label} hosts must be a non-empty array")
        else:
            unknown_hosts = sorted(
                host for host in hosts if not isinstance(host, str) or host not in ALLOWED_HOSTS
            )
            for host in unknown_hosts:
                errors.append(f"{label} has unsupported host '{host}'")
            if len(hosts) != len(set(host for host in hosts if isinstance(host, str))):
                errors.append(f"{label} has duplicate hosts")

    return errors


def _marketplace_source(entry: dict[str, Any]) -> object:
    source = entry.get("source")
    if isinstance(source, dict):
        return source.get("path")
    return source


def validate_marketplace(
    catalog: dict[str, Any], marketplace: dict[str, Any], target: str
) -> list[str]:
    catalog_plugins = {
        plugin["id"]: plugin
        for plugin in catalog.get("plugins", [])
        if isinstance(plugin, dict) and isinstance(plugin.get("id"), str)
    }
    entries = marketplace.get("plugins")
    if not isinstance(entries, list):
        return [f"{target} marketplace plugins must be an array"]

    errors: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            errors.append(f"{target} marketplace contains an invalid plugin record")
            continue
        plugin_id = entry["name"]
        if plugin_id in seen:
            errors.append(f"{target} marketplace has duplicate plugin '{plugin_id}'")
            continue
        seen.add(plugin_id)
        plugin = catalog_plugins.get(plugin_id)
        if plugin is None:
            errors.append(
                f"{target} marketplace has orphan plugin '{plugin_id}' "
                "(generator-owned record)"
            )
            continue

        expected_source = f"./{plugin['package']}"
        source = _marketplace_source(entry)
        if source != expected_source:
            errors.append(
                f"{target} marketplace plugin '{plugin_id}' source is '{source}', "
                f"expected '{expected_source}'"
            )
        if "description" in entry and entry["description"] != plugin["description"]:
            errors.append(
                f"{target} marketplace plugin '{plugin_id}' description differs "
                "from catalog"
            )

    for plugin_id in catalog_plugins:
        if plugin_id not in seen:
            errors.append(f"{target} marketplace is missing plugin '{plugin_id}'")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="validate canonical catalog and package surfaces without generated outputs",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        catalog = load_json(CATALOG_PATH)
    except ValidationFailure as error:
        print(error, file=sys.stderr)
        return 1

    errors = validate_catalog(catalog, ROOT)
    if not arguments.catalog_only:
        for target, path in MARKETPLACE_PATHS.items():
            try:
                marketplace = load_json(path)
            except ValidationFailure as error:
                errors.append(str(error))
                continue
            errors.extend(validate_marketplace(catalog, marketplace, target))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    scope = "catalog and package surfaces" if arguments.catalog_only else "repository"
    print(f"Validated {len(catalog['plugins'])} plugins ({scope}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
