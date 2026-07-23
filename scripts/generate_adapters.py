#!/usr/bin/env python3
"""Generate deterministic, package-local projections from canonical skills."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path("plugins/catalog.json")
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
FRONTMATTER_KEY_PATTERN = re.compile(r"^([a-z][a-z0-9-]*):(?:[ \t]*(.*))?$")
PORTABLE_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
}
HOST_ONLY_FRONTMATTER_FIELDS = {
    "allowed-tools",
    "background",
    "model",
    "permission",
    "proactive",
    "tools",
}
ALLOWED_CAPABILITY_KINDS = {"skill", "agent", "hybrid"}
ALLOWED_HOSTS = {"claude", "codex", "cursor", "opencode", "agent-skills"}
NATIVE_HOSTS = {"claude", "codex", "cursor"}
CLAUDE_OVERRIDE_FIELDS = {"agent_path", "description", "model"}
CLAUDE_MODELS = {"inherit", "haiku", "sonnet", "opus"}
REQUIRED_CATALOG_FIELDS = {
    "schema_version",
    "repository",
    "defaults",
    "marketplaces",
    "plugins",
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


class GenerationFailure(RuntimeError):
    """Raised when canonical inputs cannot safely produce adapters."""


def _parse_frontmatter(skill_file: Path, content: str) -> dict[str, str]:
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        raise GenerationFailure(f"{skill_file}: missing YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise GenerationFailure(f"{skill_file}: unterminated YAML frontmatter") from error

    values: dict[str, str] = {}
    current_key: str | None = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            if current_key not in {"description", "compatibility", "metadata"}:
                raise GenerationFailure(
                    f"{skill_file}: unexpected indented frontmatter content"
                )
            if current_key != "metadata":
                values[current_key] = (
                    f"{values[current_key]} {line.strip()}".strip()
                )
            continue
        match = FRONTMATTER_KEY_PATTERN.fullmatch(line)
        if match is None:
            raise GenerationFailure(
                f"{skill_file}: invalid frontmatter key syntax '{line}'"
            )
        current_key, value = match.groups()
        if current_key in values:
            raise GenerationFailure(
                f"{skill_file}: duplicate frontmatter field '{current_key}'"
            )
        values[current_key] = (value or "").strip()
        if values[current_key] in {">", "|"}:
            values[current_key] = ""
    return values


def _referenced_paths(content: str) -> set[str]:
    inline_references = re.findall(
        r"`([^`\n]+\.md(?:[?#][^`\n]*)?)`",
        content,
    )
    markdown_references = re.findall(r"\]\(([^)\n]+)\)", content)
    references: set[str] = set()
    for raw_reference in inline_references:
        reference = raw_reference.strip()
        if not (
            "/" in reference
            or reference.startswith((".", "~"))
        ):
            continue
        reference = reference.split("#", 1)[0].split("?", 1)[0].strip()
        if reference:
            references.add(reference)
    for raw_reference in markdown_references:
        reference = raw_reference.strip()
        if (
            reference.startswith(("#", "//"))
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", reference)
        ):
            continue
        reference = reference.split("#", 1)[0].split("?", 1)[0].strip()
        if reference:
            references.add(reference)
    return references


def _case_mismatch(path: Path) -> bool:
    current = path.anchor and Path(path.anchor) or Path()
    parts = path.parts[1:] if path.anchor else path.parts
    for part in parts:
        if not current.is_dir():
            return False
        entries = {entry.name: entry for entry in current.iterdir()}
        if part in entries:
            current = entries[part]
            continue
        if any(name.lower() == part.lower() for name in entries):
            return True
        return False
    return False


def validate_skill(skill_directory: Path, content: str | None = None) -> list[str]:
    errors: list[str] = []
    if skill_directory.is_symlink():
        return [f"{skill_directory}: symlink skill directories are not allowed"]
    skill_directory = skill_directory.resolve()
    skill_file = skill_directory / "SKILL.md"
    if not skill_file.is_file():
        return [f"{skill_directory}: missing SKILL.md"]
    if content is None:
        content = skill_file.read_text()

    for directory, directory_names, file_names in os.walk(
        skill_directory, followlinks=False
    ):
        base = Path(directory)
        for name in directory_names + file_names:
            candidate = base / name
            if candidate.is_symlink():
                errors.append(f"{candidate}: symlink inputs are not allowed")

    try:
        frontmatter = _parse_frontmatter(skill_file, content)
    except GenerationFailure as error:
        return errors + [str(error)]

    name = frontmatter.get("name", "")
    if not NAME_PATTERN.fullmatch(name):
        errors.append(f"{skill_file}: invalid skill name '{name}'")
    if name != skill_directory.name:
        errors.append(
            f"{skill_file}: frontmatter name '{name}' must match directory "
            f"'{skill_directory.name}'"
        )

    description = frontmatter.get("description", "").strip()
    if not description or len(description) > 1024:
        errors.append(f"{skill_file}: description must contain 1-1024 characters")

    for field in sorted(frontmatter.keys() - PORTABLE_FRONTMATTER_FIELDS):
        if field in HOST_ONLY_FRONTMATTER_FIELDS:
            errors.append(
                f"{skill_file}: host-only frontmatter '{field}' is not portable; "
                f"non-portable frontmatter field '{field}'"
            )
        else:
            errors.append(
                f"{skill_file}: non-portable frontmatter field '{field}'"
            )

    for reference in sorted(_referenced_paths(content)):
        pure_reference = PurePosixPath(reference)
        if pure_reference.is_absolute() or reference.startswith("~"):
            errors.append(f"{skill_file}: absolute reference '{reference}' is not allowed")
            continue
        if ".." in pure_reference.parts:
            errors.append(f"{skill_file}: reference '{reference}' escapes the skill directory")
            continue
        resolved = skill_directory.joinpath(*pure_reference.parts)
        if _case_mismatch(resolved):
            errors.append(f"{skill_file}: reference '{reference}' has a case mismatch")
        elif not resolved.exists():
            errors.append(f"{skill_file}: missing reference '{reference}'")
    return errors


def _tree_files(directory: Path) -> dict[str, bytes]:
    if not directory.is_dir():
        return {}
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _skill_body(content: str) -> str:
    lines = content.splitlines()
    end = lines.index("---", 1)
    return "\n".join(lines[end + 1 :]).lstrip() + "\n"


def _render_claude_agent(plugin: dict[str, Any], content: str) -> str | None:
    claude = plugin.get("overrides", {}).get("claude", {})
    if not claude.get("agent_path"):
        return None
    description = claude.get("description", plugin.get("description", ""))
    model = claude.get("model", "inherit")
    return (
        "---\n"
        f"name: {_yaml_scalar(plugin['id'])}\n"
        f"description: {_yaml_scalar(description)}\n"
        f"model: {_yaml_scalar(model)}\n"
        "---\n\n"
        "<!-- Generated from the canonical reviewer skill. Do not edit directly. -->\n\n"
        f"{_skill_body(content)}"
    )


def _json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _yaml_scalar(value: str) -> str:
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9 ./(),_+-]*", value):
        return value
    return json.dumps(value, ensure_ascii=False)


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GenerationFailure(f"{label} must be a non-empty string")
    return value


def _strict_catalog_path(
    base: Path,
    value: object,
    *,
    boundary: Path,
    label: str,
) -> Path:
    if not isinstance(value, str) or not value:
        raise GenerationFailure(f"{label} must be a non-empty relative path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "." in relative.parts
        or not relative.parts
    ):
        raise GenerationFailure(f"{label} has unsafe path '{value}'")

    base = base.absolute()
    boundary = boundary.resolve()
    candidate = base.joinpath(*relative.parts)
    current = base
    if current.is_symlink():
        raise GenerationFailure(f"{label} has symlinked ancestor '{current}'")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise GenerationFailure(f"{label} has symlinked ancestor '{current}'")

    resolved = candidate.resolve(strict=False)
    if resolved != boundary and boundary not in resolved.parents:
        raise GenerationFailure(
            f"{label} resolves outside '{boundary}': '{value}'"
        )
    return candidate


def _validate_catalog(
    catalog: dict[str, Any], root: Path
) -> dict[str, dict[str, Path | None]]:
    missing = sorted(REQUIRED_CATALOG_FIELDS - catalog.keys())
    if missing:
        raise GenerationFailure(
            f"catalog is missing required field(s): {', '.join(missing)}"
        )
    if catalog.get("schema_version") != 1:
        raise GenerationFailure("catalog schema_version must be 1")
    _require_string(catalog.get("repository"), "catalog repository")

    defaults = catalog.get("defaults")
    if not isinstance(defaults, dict):
        raise GenerationFailure("catalog defaults must be an object")
    author = defaults.get("author")
    if not isinstance(author, dict):
        raise GenerationFailure("catalog defaults.author must be an object")
    for field in ("name", "url"):
        _require_string(
            author.get(field),
            f"catalog defaults.author.{field}",
        )
    for field in ("homepage", "license", "category"):
        _require_string(defaults.get(field), f"catalog defaults.{field}")

    marketplaces = catalog.get("marketplaces")
    if not isinstance(marketplaces, dict):
        raise GenerationFailure("catalog marketplaces must be an object")
    for host in ("claude", "codex", "cursor"):
        marketplace = marketplaces.get(host)
        if not isinstance(marketplace, dict):
            raise GenerationFailure(
                f"catalog marketplaces.{host} must be an object"
            )
        for field in ("name", "display_name"):
            _require_string(
                marketplace.get(field),
                f"catalog marketplaces.{host}.{field}",
            )

    plugins = catalog.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        raise GenerationFailure("catalog plugins must be a non-empty array")

    resolved_paths: dict[str, dict[str, Path | None]] = {}
    for index, plugin in enumerate(plugins):
        if not isinstance(plugin, dict):
            raise GenerationFailure(f"catalog plugin at index {index} must be an object")
        missing_plugin = sorted(REQUIRED_PLUGIN_FIELDS - plugin.keys())
        if missing_plugin:
            raise GenerationFailure(
                f"catalog plugin at index {index} is missing field(s): "
                f"{', '.join(missing_plugin)}"
            )
        plugin_id = _require_string(
            plugin.get("id"), f"catalog plugin at index {index} id"
        )
        if not NAME_PATTERN.fullmatch(plugin_id):
            raise GenerationFailure(f"plugin '{plugin_id}' has invalid id")
        if plugin_id in resolved_paths:
            raise GenerationFailure(f"duplicate plugin id '{plugin_id}'")
        version = _require_string(
            plugin.get("version"), f"plugin '{plugin_id}' version"
        )
        if not SEMVER_PATTERN.fullmatch(version):
            raise GenerationFailure(
                f"plugin '{plugin_id}' has invalid version '{version}'"
            )
        _require_string(
            plugin.get("description"), f"plugin '{plugin_id}' description"
        )

        hosts = plugin.get("hosts")
        if not isinstance(hosts, list) or not hosts:
            raise GenerationFailure(
                f"plugin '{plugin_id}' hosts must be a non-empty array"
            )
        if len(hosts) != len(set(host for host in hosts if isinstance(host, str))):
            raise GenerationFailure(f"plugin '{plugin_id}' has duplicate hosts")
        unsupported_hosts = [
            host
            for host in hosts
            if not isinstance(host, str) or host not in ALLOWED_HOSTS
        ]
        if unsupported_hosts:
            raise GenerationFailure(
                f"plugin '{plugin_id}' has unsupported host "
                f"'{unsupported_hosts[0]}'"
            )
        missing_portable_hosts = sorted(
            {"opencode", "agent-skills"} - set(hosts)
        )
        if missing_portable_hosts:
            raise GenerationFailure(
                f"plugin '{plugin_id}' must support the canonical portable "
                f"host(s): {', '.join(missing_portable_hosts)}"
            )

        package = _strict_catalog_path(
            root,
            plugin.get("package"),
            boundary=root / "plugins",
            label=f"plugin '{plugin_id}' package",
        )
        if package.parent != (root / "plugins").resolve():
            raise GenerationFailure(
                f"plugin '{plugin_id}' package must be a direct child of 'plugins/'"
            )
        if not package.is_dir():
            raise GenerationFailure(
                f"plugin '{plugin_id}' package does not exist: "
                f"'{plugin.get('package')}'"
            )

        capability = plugin.get("capability")
        if not isinstance(capability, dict):
            raise GenerationFailure(
                f"plugin '{plugin_id}' capability must be an object"
            )
        kind = capability.get("kind")
        if kind not in ALLOWED_CAPABILITY_KINDS:
            raise GenerationFailure(
                f"plugin '{plugin_id}' has unsupported capability kind '{kind}'"
            )
        canonical_file = _strict_catalog_path(
            root,
            capability.get("canonical_path"),
            boundary=root,
            label=f"plugin '{plugin_id}' capability.canonical_path",
        )
        package_file = _strict_catalog_path(
            package,
            capability.get("package_path"),
            boundary=package,
            label=f"plugin '{plugin_id}' capability.package_path",
        )
        if canonical_file.name != "SKILL.md" or package_file.name != "SKILL.md":
            raise GenerationFailure(
                f"plugin '{plugin_id}' skill paths must point to SKILL.md"
            )
        legacy_file = None
        if capability.get("legacy_package_path") is not None:
            legacy_file = _strict_catalog_path(
                package,
                capability.get("legacy_package_path"),
                boundary=package,
                label=f"plugin '{plugin_id}' capability.legacy_package_path",
            )

        overrides = plugin.get("overrides", {})
        if not isinstance(overrides, dict):
            raise GenerationFailure(
                f"plugin '{plugin_id}' overrides must be an object"
            )
        claude = overrides.get("claude", {})
        if not isinstance(claude, dict):
            raise GenerationFailure(
                f"plugin '{plugin_id}' Claude override must be an object"
            )
        unknown_override_fields = sorted(
            set(claude) - CLAUDE_OVERRIDE_FIELDS
        )
        if unknown_override_fields:
            raise GenerationFailure(
                f"plugin '{plugin_id}' has unsupported Claude override "
                f"field '{unknown_override_fields[0]}'"
            )
        agent_file = None
        if "agent_path" in claude:
            agent_file = _strict_catalog_path(
                package,
                claude.get("agent_path"),
                boundary=package,
                label=f"plugin '{plugin_id}' Claude agent_path",
            )
        if agent_file is not None and kind not in {"agent", "hybrid"}:
            raise GenerationFailure(
                f"plugin '{plugin_id}' Claude agent_path requires an "
                "agent or hybrid capability"
            )
        if (
            "claude" in hosts
            and kind in {"agent", "hybrid"}
            and agent_file is None
        ):
            raise GenerationFailure(
                f"plugin '{plugin_id}' requires a Claude agent_path"
            )
        if "description" in claude:
            _require_string(
                claude.get("description"),
                f"plugin '{plugin_id}' Claude description",
            )
        if "model" in claude and claude.get("model") not in CLAUDE_MODELS:
            raise GenerationFailure(
                f"plugin '{plugin_id}' has invalid Claude model "
                f"'{claude.get('model')}'"
            )

        interface = plugin.get("interface")
        if not isinstance(interface, dict):
            raise GenerationFailure(
                f"plugin '{plugin_id}' interface must be an object"
            )
        for field in (
            "display_name",
            "short_description",
            "long_description",
        ):
            _require_string(
                interface.get(field),
                f"plugin '{plugin_id}' interface.{field}",
            )
        prompts = interface.get("default_prompts")
        if (
            not isinstance(prompts, list)
            or not prompts
            or any(not isinstance(prompt, str) or not prompt for prompt in prompts)
        ):
            raise GenerationFailure(
                f"plugin '{plugin_id}' interface.default_prompts "
                "must be a non-empty string array"
            )

        resolved_paths[plugin_id] = {
            "package": package,
            "canonical_file": canonical_file,
            "package_file": package_file,
            "legacy_file": legacy_file,
            "agent_file": agent_file,
        }
    return resolved_paths


def _semver_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def _interface(plugin: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    interface = plugin["interface"]
    override = plugin.get("overrides", {}).get("codex", {})
    capabilities = (
        ["Interactive", "Review"]
        if plugin["capability"]["kind"] == "hybrid"
        else ["Interactive", "Write"]
    )
    value: dict[str, Any] = {
        "displayName": interface["display_name"],
        "shortDescription": interface["short_description"],
        "longDescription": interface["long_description"],
        "developerName": defaults["author"]["name"],
        "category": defaults["category"],
        "capabilities": capabilities,
        "websiteURL": override.get("website_url", defaults["homepage"]),
        "defaultPrompt": interface["default_prompts"],
    }
    optional_fields = {
        "privacyPolicyURL": override.get("privacy_policy_url"),
        "termsOfServiceURL": override.get("terms_of_service_url"),
    }
    value.update({key: item for key, item in optional_fields.items() if item})
    return value


def _native_outputs(
    catalog: dict[str, Any], root: Path
) -> list[tuple[str, Path]]:
    defaults = catalog["defaults"]
    outputs: list[tuple[str, Path]] = []
    claude_plugins: list[dict[str, Any]] = []
    codex_plugins: list[dict[str, Any]] = []
    cursor_plugins: list[dict[str, Any]] = []
    versions: list[str] = []

    for plugin in catalog["plugins"]:
        versions.append(plugin["version"])
        package = root / plugin["package"]
        hosts = set(plugin["hosts"])
        skill_root = (
            "./portable-skills/"
            if plugin["capability"]["kind"] == "hybrid"
            else "./skills/"
        )
        claude_manifest = {
            "name": plugin["id"],
            "version": plugin["version"],
            "description": plugin["description"],
            "author": defaults["author"],
            "homepage": defaults["homepage"],
            "repository": catalog["repository"],
            "license": defaults["license"],
            "keywords": plugin["keywords"],
        }
        codex_manifest = {
            **claude_manifest,
            "skills": skill_root,
            "interface": _interface(plugin, defaults),
        }
        cursor_manifest = {
            "name": plugin["id"],
            "displayName": plugin["interface"]["display_name"],
            "version": plugin["version"],
            "description": plugin["description"],
            "author": {"name": defaults["author"]["name"]},
            "homepage": defaults["homepage"],
            "repository": catalog["repository"],
            "license": defaults["license"],
            "keywords": plugin["keywords"],
            "category": defaults["category"],
            "skills": skill_root,
        }
        if "claude" in hosts:
            outputs.append(
                (
                    _json_text(claude_manifest),
                    package / ".claude-plugin" / "plugin.json",
                )
            )
            claude_plugins.append(
                {
                    "name": plugin["id"],
                    "source": f"./{plugin['package']}",
                    "description": plugin["description"],
                    "category": "development",
                }
            )
        if "codex" in hosts:
            outputs.append(
                (
                    _json_text(codex_manifest),
                    package / ".codex-plugin" / "plugin.json",
                )
            )
            codex_plugins.append(
                {
                    "name": plugin["id"],
                    "source": {
                        "source": "local",
                        "path": f"./{plugin['package']}",
                    },
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": defaults["category"],
                }
            )
        if "cursor" in hosts:
            outputs.append(
                (
                    _json_text(cursor_manifest),
                    package / ".cursor-plugin" / "plugin.json",
                )
            )
            cursor_plugins.append(
                {
                    "name": plugin["id"],
                    "source": f"./{plugin['package']}",
                    "description": plugin["description"],
                }
            )

    collection_version = max(versions, key=_semver_key)
    outputs.extend(
        (
            (
                _json_text(
                    {
                        "name": catalog["marketplaces"]["claude"]["name"],
                        "version": collection_version,
                        "description": "Django skills and agents for AI-assisted development",
                        "owner": {"name": defaults["author"]["name"]},
                        "plugins": claude_plugins,
                    }
                ),
                root / ".claude-plugin" / "marketplace.json",
            ),
            (
                _json_text(
                    {
                        "name": catalog["marketplaces"]["codex"]["name"],
                        "interface": {
                            "displayName": catalog["marketplaces"]["codex"][
                                "display_name"
                            ]
                        },
                        "plugins": codex_plugins,
                    }
                ),
                root / ".agents" / "plugins" / "marketplace.json",
            ),
            (
                _json_text(
                    {
                        "name": catalog["marketplaces"]["cursor"]["name"],
                        "owner": {"name": defaults["author"]["name"]},
                        "metadata": {
                            "description": (
                                "Django skills for AI-assisted development"
                            ),
                            "version": collection_version,
                        },
                        "plugins": cursor_plugins,
                    }
                ),
                root / ".cursor-plugin" / "marketplace.json",
            ),
        )
    )
    return outputs


def _load_catalog(root: Path) -> dict[str, Any]:
    path = root / CATALOG_PATH
    try:
        value = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise GenerationFailure(f"{path}: cannot load catalog: {error}") from error
    if not isinstance(value, dict):
        raise GenerationFailure(f"{path}: catalog root must be an object")
    return value


def _needs_skill_projection(plugin: dict[str, Any]) -> bool:
    native_hosts = set(plugin["hosts"]) & NATIVE_HOSTS
    kind = plugin["capability"]["kind"]
    if kind == "agent":
        return False
    if kind == "hybrid":
        return bool(native_hosts & {"codex", "cursor"})
    return bool(native_hosts)


def _skill_projection(
    plugin: dict[str, Any],
    resolved: dict[str, Path | None],
) -> tuple[Path, Path] | None:
    if not _needs_skill_projection(plugin):
        return None
    canonical_file = resolved["canonical_file"]
    package_file = resolved["package_file"]
    assert isinstance(canonical_file, Path)
    assert isinstance(package_file, Path)
    if canonical_file.name != "SKILL.md" or package_file.name != "SKILL.md":
        raise GenerationFailure(
            f"plugin '{plugin.get('id')}' skill paths must point to SKILL.md"
        )
    return canonical_file.parent, package_file.parent


def _replace_directory(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    replacement = target.parent / f".{target.name}.new-{token}"
    backup = target.parent / f".{target.name}.old-{token}"
    os.replace(staged, replacement)
    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
        os.replace(replacement, target)
    except Exception:
        if replacement.exists():
            shutil.rmtree(replacement)
        if had_target and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def _replace_file(content: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.new-{uuid.uuid4().hex}"
    temporary.write_text(content)
    os.replace(temporary, target)


def _remove_legacy_projection(legacy_file: Path | None) -> None:
    if legacy_file is None:
        return
    if legacy_file.is_file() or legacy_file.is_symlink():
        legacy_file.unlink()
    legacy_references = legacy_file.parent / "references"
    if legacy_references.is_dir():
        shutil.rmtree(legacy_references)


def _orphan_generated_paths(
    catalog: dict[str, Any],
    root: Path,
    resolved_paths: dict[str, dict[str, Path | None]],
) -> list[Path]:
    declared_packages = {
        resolved["package"]
        for resolved in resolved_paths.values()
    }
    orphans: list[Path] = []
    for package in sorted((root / "plugins").iterdir()):
        if (
            not package.is_dir()
            or package.is_symlink()
            or package in declared_packages
        ):
            continue
        manifests = [
            package / f".{target}-plugin" / "plugin.json"
            for target in ("claude", "codex", "cursor")
        ]
        manifests = [path for path in manifests if path.is_file()]
        if not manifests:
            continue
        names: set[object] = set()
        for path in manifests:
            try:
                manifest = json.loads(path.read_text())
            except json.JSONDecodeError as error:
                raise GenerationFailure(
                    f"{path}: invalid JSON in generated orphan manifest "
                    f"at line {error.lineno}, column {error.colno}"
                ) from error
            if not isinstance(manifest, dict):
                raise GenerationFailure(
                    f"{path}: generated orphan manifest must be an object"
                )
            names.add(manifest.get("name"))
        if (
            len(names) != 1
            or not isinstance(next(iter(names)), str)
            or not NAME_PATTERN.fullmatch(next(iter(names)))
        ):
            continue
        plugin_id = next(iter(names))
        orphans.extend(manifests)
        for skill in (
            package / "skills" / plugin_id,
            package / "portable-skills" / plugin_id,
        ):
            if skill.is_dir() and not skill.is_symlink():
                orphans.append(skill)
        agent = package / "agents" / f"{plugin_id}.md"
        if (
            agent.is_file()
            and "Generated from the canonical reviewer skill" in agent.read_text()
        ):
            orphans.append(agent)
    return orphans


def _disabled_generated_paths(
    catalog: dict[str, Any],
    resolved_paths: dict[str, dict[str, Path | None]],
) -> list[Path]:
    disabled: list[Path] = []
    for plugin in catalog["plugins"]:
        resolved = resolved_paths[plugin["id"]]
        package = resolved["package"]
        assert isinstance(package, Path)
        hosts = set(plugin["hosts"])
        for host in sorted(NATIVE_HOSTS - hosts):
            manifest = package / f".{host}-plugin" / "plugin.json"
            if manifest.is_file():
                disabled.append(manifest)

        package_file = resolved["package_file"]
        assert isinstance(package_file, Path)
        package_skill = package_file.parent
        if not _needs_skill_projection(plugin) and package_skill.is_dir():
            disabled.append(package_skill)

        agent_file = resolved["agent_file"]
        if (
            "claude" not in hosts
            and isinstance(agent_file, Path)
            and agent_file.is_file()
            and "Generated from the canonical reviewer skill"
            in agent_file.read_text()
        ):
            disabled.append(agent_file)
    return disabled


def _remove_generated_path(path: Path) -> None:
    parent = path.parent
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()
    if parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif _path_exists(path):
        path.unlink()


class _MutationJournal:
    def __init__(self, root: Path, journal_root: Path, targets: list[Path]):
        self.root = root
        self.journal_root = journal_root
        self.targets = self._without_nested_targets(targets)
        self.backups: list[tuple[Path, Path | None]] = []
        self.missing_parents: set[Path] = set()

    @staticmethod
    def _without_nested_targets(targets: list[Path]) -> list[Path]:
        unique = sorted(set(targets), key=lambda path: (len(path.parts), str(path)))
        selected: list[Path] = []
        for path in unique:
            if any(parent == path or parent in path.parents for parent in selected):
                continue
            selected.append(path)
        return selected

    def snapshot(self) -> None:
        backup_root = self.journal_root / "rollback"
        backup_root.mkdir()
        for index, target in enumerate(self.targets):
            parent = target.parent
            while parent != self.root and self.root in parent.parents:
                if not parent.exists():
                    self.missing_parents.add(parent)
                parent = parent.parent
            if not _path_exists(target):
                self.backups.append((target, None))
                continue
            backup = backup_root / str(index)
            if target.is_dir() and not target.is_symlink():
                shutil.copytree(target, backup)
            elif target.is_symlink():
                backup.symlink_to(os.readlink(target))
            else:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            self.backups.append((target, backup))

    def rollback(self) -> None:
        for target, _ in sorted(
            self.backups,
            key=lambda item: len(item[0].parts),
            reverse=True,
        ):
            _remove_path(target)
        for target, backup in self.backups:
            if backup is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if backup.is_dir() and not backup.is_symlink():
                shutil.copytree(backup, target)
            elif backup.is_symlink():
                target.symlink_to(os.readlink(backup))
            else:
                shutil.copy2(backup, target)
        for parent in sorted(
            self.missing_parents,
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()


def generate_adapters(root: Path = ROOT, check: bool = False) -> list[str]:
    root = root.resolve()
    catalog = _load_catalog(root)
    resolved_paths = _validate_catalog(catalog, root)
    projections: list[tuple[dict[str, Any], Path, Path]] = []
    generated_files: list[tuple[str, Path]] = []
    validation_errors: list[str] = []
    for plugin in catalog["plugins"]:
        resolved = resolved_paths[plugin["id"]]
        canonical_file = resolved["canonical_file"]
        assert isinstance(canonical_file, Path)
        source = canonical_file.parent
        source_content = canonical_file.read_text()
        validation_errors.extend(validate_skill(source, source_content))

        projection = _skill_projection(plugin, resolved)
        if projection is not None:
            _, target = projection
            projections.append((plugin, source, target))

        agent_file = resolved["agent_file"]
        if "claude" in plugin["hosts"] and isinstance(agent_file, Path):
            agent_content = _render_claude_agent(plugin, source_content)
            assert agent_content is not None
            generated_files.append(
                (
                    agent_content,
                    agent_file,
                )
            )
    if validation_errors:
        raise GenerationFailure("\n".join(validation_errors))
    generated_files.extend(_native_outputs(catalog, root))
    orphan_paths = _orphan_generated_paths(catalog, root, resolved_paths)
    disabled_paths = _disabled_generated_paths(catalog, resolved_paths)

    changed: list[str] = []
    for _, source, target in projections:
        if _tree_files(source) != _tree_files(target):
            changed.append(str(target.relative_to(root)))
    legacy_paths: list[Path] = []
    for plugin in catalog["plugins"]:
        resolved = resolved_paths[plugin["id"]]
        legacy_file = resolved["legacy_file"]
        if isinstance(legacy_file, Path) and (
            _path_exists(legacy_file)
            or (legacy_file.parent / "references").is_dir()
        ):
            legacy_paths.extend(
                [legacy_file, legacy_file.parent / "references"]
            )
            package_file = resolved["package_file"]
            assert isinstance(package_file, Path)
            relative_target = str(package_file.parent.relative_to(root))
            if relative_target not in changed:
                changed.append(relative_target)
    for content, target in generated_files:
        if not target.is_file() or target.read_text() != content:
            changed.append(str(target.relative_to(root)))
    deletion_paths = sorted(set(orphan_paths + disabled_paths))
    changed.extend(str(path.relative_to(root)) for path in deletion_paths)

    changed = sorted(set(changed))
    if check or not changed:
        return changed

    with tempfile.TemporaryDirectory(prefix=".adapter-stage-", dir=root) as temporary:
        stage_root = Path(temporary)
        staged: list[tuple[dict[str, Any], Path, Path]] = []
        for plugin, source, target in projections:
            if str(target.relative_to(root)) not in changed:
                continue
            stage = stage_root / plugin["id"]
            shutil.copytree(source, stage)
            staged.append((plugin, stage, target))

        changed_files = [
            target
            for _, target in generated_files
            if str(target.relative_to(root)) in changed
        ]
        mutation_targets = (
            [target for _, _, target in staged]
            + legacy_paths
            + deletion_paths
            + changed_files
        )
        journal = _MutationJournal(root, stage_root, mutation_targets)
        journal.snapshot()
        try:
            for _, stage, target in staged:
                _replace_directory(stage, target)
            for plugin in catalog["plugins"]:
                legacy_file = resolved_paths[plugin["id"]]["legacy_file"]
                _remove_legacy_projection(
                    legacy_file if isinstance(legacy_file, Path) else None
                )
            for path in deletion_paths:
                _remove_generated_path(path)
            for content, target in generated_files:
                if str(target.relative_to(root)) in changed:
                    _replace_file(content, target)
        except Exception as error:
            journal.rollback()
            raise GenerationFailure(
                f"adapter generation transaction failed: {error}"
            ) from error
    return changed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report generated drift without modifying the repository",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        changed = generate_adapters(ROOT, check=arguments.check)
    except GenerationFailure as error:
        print(error, file=sys.stderr)
        return 1

    if arguments.check and changed:
        for path in changed:
            print(f"OUTDATED: {path}", file=sys.stderr)
        return 1
    if changed:
        print(f"Generated {len(changed)} adapter projection(s).")
    else:
        print("Generated adapters are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
