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
REQUIRED_CATALOG_FIELDS = {
    "schema_version",
    "repository",
    "defaults",
    "marketplaces",
    "plugins",
}
ALLOWED_CAPABILITY_KINDS = {"skill", "agent", "hybrid"}
ALLOWED_HOSTS = {"claude", "codex", "cursor", "opencode", "agent-skills"}
NATIVE_HOSTS = {"claude", "codex", "cursor"}
CLAUDE_OVERRIDE_FIELDS = {"agent_path", "description", "model"}
CLAUDE_MODELS = {"inherit", "haiku", "sonnet", "opus"}
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


def _resolve_catalog_path(
    base: Path,
    value: object,
    *,
    boundary: Path,
) -> tuple[Path | None, str | None]:
    relative = _safe_relative_path(value)
    if relative is None:
        return None, f"unsafe path '{value}'"
    base = base.absolute()
    boundary = boundary.resolve()
    candidate = base.joinpath(*relative.parts)
    current = base
    if current.is_symlink():
        return None, f"symlinked ancestor '{current}'"
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None, f"symlinked ancestor '{current}'"
    resolved = candidate.resolve(strict=False)
    if resolved != boundary and boundary not in resolved.parents:
        return None, f"path '{value}' resolves outside '{boundary}'"
    return candidate, None


def _needs_skill_projection(plugin: dict[str, Any]) -> bool:
    hosts = plugin.get("hosts")
    if not isinstance(hosts, list):
        return False
    native_hosts = set(
        host for host in hosts if isinstance(host, str)
    ) & NATIVE_HOSTS
    capability = plugin.get("capability")
    if not isinstance(capability, dict):
        return False
    kind = capability.get("kind")
    if kind == "agent":
        return False
    if kind == "hybrid":
        return bool(native_hosts & {"codex", "cursor"})
    return bool(native_hosts)


def _plugin_label(plugin: object, index: int) -> str:
    if isinstance(plugin, dict) and isinstance(plugin.get("id"), str):
        return f"plugin '{plugin['id']}'"
    return f"plugin at index {index}"


def validate_catalog(catalog: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for field in sorted(REQUIRED_CATALOG_FIELDS - catalog.keys()):
        errors.append(f"catalog is missing required field '{field}'")
    if catalog.get("schema_version") != 1:
        errors.append("catalog schema_version must be 1")
    if not isinstance(catalog.get("repository"), str) or not catalog[
        "repository"
    ].strip():
        errors.append("catalog repository must be a non-empty string")
    defaults = catalog.get("defaults")
    if not isinstance(defaults, dict):
        errors.append("catalog defaults must be an object")
    else:
        author = defaults.get("author")
        if not isinstance(author, dict):
            errors.append("catalog defaults.author must be an object")
        else:
            for field in ("name", "url"):
                if (
                    not isinstance(author.get(field), str)
                    or not author[field].strip()
                ):
                    errors.append(
                        f"catalog defaults.author.{field} must be "
                        "a non-empty string"
                    )
        for field in ("homepage", "license", "category"):
            if (
                not isinstance(defaults.get(field), str)
                or not defaults[field].strip()
            ):
                errors.append(
                    f"catalog defaults.{field} must be a non-empty string"
                )
    marketplaces = catalog.get("marketplaces")
    if not isinstance(marketplaces, dict):
        errors.append("catalog marketplaces must be an object")
    else:
        for host in ("claude", "codex", "cursor"):
            marketplace = marketplaces.get(host)
            if not isinstance(marketplace, dict):
                errors.append(f"catalog marketplaces.{host} must be an object")
                continue
            for field in ("name", "display_name"):
                if (
                    not isinstance(marketplace.get(field), str)
                    or not marketplace[field].strip()
                ):
                    errors.append(
                        f"catalog marketplaces.{host}.{field} must be "
                        "a non-empty string"
                    )

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
        package_root: Path | None = None
        package_exists = False
        package_root, package_error = _resolve_catalog_path(
            root,
            package_value,
            boundary=root / "plugins",
        )
        if package_error is not None:
            errors.append(f"{label} package has {package_error}")
        else:
            assert package_root is not None
            package_exists = package_root.is_dir()
            if not package_exists:
                errors.append(f"{label} references unknown package root '{package_value}'")
            if package_root.parent != (root / "plugins").resolve():
                errors.append(
                    f"{label} package must be a direct child of 'plugins/'"
                )

        capability = plugin.get("capability")
        if not isinstance(capability, dict):
            errors.append(f"{label} capability must be an object")
        else:
            kind = capability.get("kind")
            if kind not in ALLOWED_CAPABILITY_KINDS:
                errors.append(f"{label} has unsupported capability kind '{kind}'")
            canonical_value = capability.get("canonical_path")
            _, canonical_error = _resolve_catalog_path(
                root,
                canonical_value,
                boundary=root,
            )
            if canonical_error is not None:
                errors.append(
                    f"{label} canonical capability path has {canonical_error}"
                )
            surface_value = capability.get("package_path")
            surface: Path | None = None
            if package_root is not None:
                surface, surface_error = _resolve_catalog_path(
                    package_root,
                    surface_value,
                    boundary=package_root,
                )
            else:
                surface_error = f"unsafe path '{surface_value}'"
            if surface_error is not None:
                errors.append(
                    f"{label} package capability path has {surface_error}"
                )
            elif package_exists and _needs_skill_projection(plugin):
                assert surface is not None
                if not surface.is_file():
                    errors.append(
                        f"{label} advertises no usable surface at "
                        f"'{package_value}/{surface_value}'"
                    )
            legacy_value = capability.get("legacy_package_path")
            if legacy_value is not None and package_root is not None:
                _, legacy_error = _resolve_catalog_path(
                    package_root,
                    legacy_value,
                    boundary=package_root,
                )
                if legacy_error is not None:
                    errors.append(
                        f"{label} legacy capability path has {legacy_error}"
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
            missing_portable_hosts = sorted(
                {"opencode", "agent-skills"} - set(hosts)
            )
            if missing_portable_hosts:
                errors.append(
                    f"{label} canonical skills require host(s): "
                    f"{', '.join(missing_portable_hosts)}"
                )

        overrides = plugin.get("overrides", {})
        if not isinstance(overrides, dict):
            errors.append(f"{label} overrides must be an object")
        else:
            claude = overrides.get("claude", {})
            if not isinstance(claude, dict):
                errors.append(f"{label} Claude override must be an object")
            else:
                unknown_fields = sorted(
                    set(claude) - CLAUDE_OVERRIDE_FIELDS
                )
                for field in unknown_fields:
                    errors.append(
                        f"{label} has unsupported Claude override field '{field}'"
                    )
                model = claude.get("model")
                if model is not None and model not in CLAUDE_MODELS:
                    errors.append(f"{label} has invalid Claude model '{model}'")
                if "agent_path" in claude and package_root is not None:
                    _, agent_error = _resolve_catalog_path(
                        package_root,
                        claude.get("agent_path"),
                        boundary=package_root,
                    )
                    if agent_error is not None:
                        errors.append(
                            f"{label} Claude agent path has {agent_error}"
                        )

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
        if (
            isinstance(plugin, dict)
            and isinstance(plugin.get("id"), str)
            and target in plugin.get("hosts", [])
        )
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
