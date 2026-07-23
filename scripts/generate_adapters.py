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
HOST_ONLY_FRONTMATTER = {
    "allowed-tools",
    "background",
    "model",
    "permission",
    "proactive",
    "tools",
}


class GenerationFailure(RuntimeError):
    """Raised when canonical inputs cannot safely produce adapters."""


def _parse_frontmatter(skill_file: Path) -> dict[str, str]:
    content = skill_file.read_text()
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
        if line.startswith((" ", "\t")) and current_key is not None:
            values[current_key] = f"{values[current_key]} {line.strip()}".strip()
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        values[current_key] = value.strip()
        if values[current_key] in {">", "|"}:
            values[current_key] = ""
    return values


def _referenced_paths(content: str) -> set[str]:
    references = set(re.findall(r"`([^`\n]+\.md)`", content))
    references.update(re.findall(r"\]\(([^)\n]+)\)", content))
    return {
        reference.strip()
        for reference in references
        if not reference.startswith(("http://", "https://", "#"))
        and (
            "/" in reference
            or reference.startswith((".", "~"))
        )
    }


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


def validate_skill(skill_directory: Path) -> list[str]:
    errors: list[str] = []
    if skill_directory.is_symlink():
        return [f"{skill_directory}: symlink skill directories are not allowed"]
    skill_directory = skill_directory.resolve()
    skill_file = skill_directory / "SKILL.md"
    if not skill_file.is_file():
        return [f"{skill_directory}: missing SKILL.md"]

    for directory, directory_names, file_names in os.walk(
        skill_directory, followlinks=False
    ):
        base = Path(directory)
        for name in directory_names + file_names:
            candidate = base / name
            if candidate.is_symlink():
                errors.append(f"{candidate}: symlink inputs are not allowed")

    try:
        frontmatter = _parse_frontmatter(skill_file)
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

    for field in sorted(HOST_ONLY_FRONTMATTER & frontmatter.keys()):
        errors.append(f"{skill_file}: host-only frontmatter '{field}' is not portable")

    for reference in sorted(_referenced_paths(skill_file.read_text())):
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


def _skill_body(skill_file: Path) -> str:
    content = skill_file.read_text()
    lines = content.splitlines()
    end = lines.index("---", 1)
    return "\n".join(lines[end + 1 :]).lstrip() + "\n"


def _render_claude_agent(plugin: dict[str, Any], source: Path) -> str | None:
    claude = plugin.get("overrides", {}).get("claude", {})
    if not claude.get("agent_path"):
        return None
    description = claude.get("description", plugin.get("description", ""))
    model = claude.get("model", "inherit")
    return (
        "---\n"
        f"name: {plugin['id']}\n"
        f"description: {description}\n"
        f"model: {model}\n"
        "---\n\n"
        "<!-- Generated from the canonical reviewer skill. Do not edit directly. -->\n\n"
        f"{_skill_body(source / 'SKILL.md')}"
    )


def _json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


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
) -> list[tuple[str, str, Path]]:
    if not catalog.get("marketplaces") or not catalog.get("defaults"):
        return []
    defaults = catalog["defaults"]
    outputs: list[tuple[str, str, Path]] = []
    claude_plugins: list[dict[str, Any]] = []
    codex_plugins: list[dict[str, Any]] = []
    cursor_plugins: list[dict[str, Any]] = []
    versions: list[str] = []

    for plugin in catalog["plugins"]:
        versions.append(plugin["version"])
        package = root / plugin["package"]
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
            "skills": (
                "./portable-skills/"
                if plugin["capability"]["kind"] == "hybrid"
                else "./skills/"
            ),
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
            "skills": (
                "./portable-skills/"
                if plugin["capability"]["kind"] == "hybrid"
                else "./skills/"
            ),
        }
        outputs.extend(
            (
                (
                    plugin["id"],
                    _json_text(claude_manifest),
                    package / ".claude-plugin" / "plugin.json",
                ),
                (
                    plugin["id"],
                    _json_text(codex_manifest),
                    package / ".codex-plugin" / "plugin.json",
                ),
                (
                    plugin["id"],
                    _json_text(cursor_manifest),
                    package / ".cursor-plugin" / "plugin.json",
                ),
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
        cursor_plugins.append(
            {
                "name": plugin["id"],
                "source": f"./{plugin['package']}",
                "description": plugin["description"],
            }
        )

    collection_version = max(versions)
    outputs.extend(
        (
            (
                "claude-marketplace",
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
                "codex-marketplace",
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
                "cursor-marketplace",
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


def _skill_projection(plugin: dict[str, Any], root: Path) -> tuple[Path, Path] | None:
    capability = plugin.get("capability", {})
    canonical_value = capability.get("canonical_path")
    package_value = capability.get("package_path")
    if not canonical_value or not package_value:
        return None
    canonical_file = root / canonical_value
    package_file = root / plugin["package"] / package_value
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
    shutil.copytree(staged, replacement)
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


def _remove_legacy_projection(plugin: dict[str, Any], root: Path) -> None:
    capability = plugin["capability"]
    legacy_value = capability.get("legacy_package_path")
    if not legacy_value:
        return
    legacy_file = root / plugin["package"] / legacy_value
    if legacy_file.is_file() or legacy_file.is_symlink():
        legacy_file.unlink()
    legacy_references = legacy_file.parent / "references"
    if legacy_references.is_dir():
        shutil.rmtree(legacy_references)


def _orphan_generated_paths(
    catalog: dict[str, Any], root: Path
) -> list[Path]:
    declared_packages = {
        (root / plugin["package"]).resolve()
        for plugin in catalog.get("plugins", [])
        if isinstance(plugin, dict) and isinstance(plugin.get("package"), str)
    }
    orphans: list[Path] = []
    for package in sorted((root / "plugins").iterdir()):
        if not package.is_dir() or package.resolve() in declared_packages:
            continue
        manifests = [
            package / f".{target}-plugin" / "plugin.json"
            for target in ("claude", "codex", "cursor")
        ]
        if not all(path.is_file() for path in manifests):
            continue
        try:
            names = {json.loads(path.read_text()).get("name") for path in manifests}
        except json.JSONDecodeError:
            continue
        if names != {package.name}:
            continue
        orphans.extend(manifests)
        for skill in (
            package / "skills" / package.name,
            package / "portable-skills" / package.name,
        ):
            if skill.is_dir() and not skill.is_symlink():
                orphans.append(skill)
        agent = package / "agents" / f"{package.name}.md"
        if (
            agent.is_file()
            and "Generated from the canonical reviewer skill" in agent.read_text()
        ):
            orphans.append(agent)
    return orphans


def _remove_generated_path(path: Path) -> None:
    parent = path.parent
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()
    if parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def generate_adapters(root: Path = ROOT, check: bool = False) -> list[str]:
    root = root.resolve()
    catalog = _load_catalog(root)
    projections: list[tuple[dict[str, Any], Path, Path]] = []
    generated_files: list[tuple[str, str, Path]] = []
    validation_errors: list[str] = []
    for plugin in catalog.get("plugins", []):
        if not isinstance(plugin, dict):
            continue
        projection = _skill_projection(plugin, root)
        if projection is None:
            continue
        source, target = projection
        errors = validate_skill(source)
        validation_errors.extend(errors)
        projections.append((plugin, source, target))
        agent_content = _render_claude_agent(plugin, source)
        agent_path = plugin.get("overrides", {}).get("claude", {}).get("agent_path")
        if agent_content is not None and agent_path:
            generated_files.append(
                (
                    plugin["id"],
                    agent_content,
                    root / plugin["package"] / agent_path,
                )
            )
    if validation_errors:
        raise GenerationFailure("\n".join(validation_errors))
    generated_files.extend(_native_outputs(catalog, root))
    orphan_paths = _orphan_generated_paths(catalog, root)

    changed: list[str] = []
    for _, source, target in projections:
        if _tree_files(source) != _tree_files(target):
            changed.append(str(target.relative_to(root)))
    for plugin, _, _ in projections:
        legacy = plugin["capability"].get("legacy_package_path")
        if legacy and (root / plugin["package"] / legacy).exists():
            target_directory = root / plugin["package"] / Path(
                plugin["capability"]["package_path"]
            ).parent
            relative_target = str(target_directory.relative_to(root))
            if relative_target not in changed:
                changed.append(relative_target)
    for _, content, target in generated_files:
        if not target.is_file() or target.read_text() != content:
            changed.append(str(target.relative_to(root)))
    changed.extend(str(path.relative_to(root)) for path in orphan_paths)

    changed = sorted(set(changed))
    if check or not changed:
        return changed

    with tempfile.TemporaryDirectory(prefix=".adapter-stage-", dir=root) as temporary:
        stage_root = Path(temporary)
        staged: list[tuple[dict[str, Any], Path, Path]] = []
        for plugin, source, target in projections:
            stage = stage_root / plugin["id"]
            shutil.copytree(source, stage)
            staged.append((plugin, stage, target))

        for plugin, stage, target in staged:
            if str(target.relative_to(root)) in changed:
                _replace_directory(stage, target)
            _remove_legacy_projection(plugin, root)
        for path in orphan_paths:
            _remove_generated_path(path)
        for _, content, target in generated_files:
            if str(target.relative_to(root)) in changed:
                _replace_file(content, target)
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
