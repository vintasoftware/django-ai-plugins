# Contributor instructions

## Source of truth

- `plugins/catalog.json` owns plugin IDs, versions, descriptions, packages,
  supported hosts, and shared marketplace metadata.
- `skills/<id>/` owns portable behavior and its local references.
- `skills/django-reviewer/` owns the shared reviewer behavior. Claude-only agent
  metadata is declared as a catalog override.

Do not edit generated files directly. This includes root marketplace JSON,
package manifests, package-local skill projections, and
`plugins/django-reviewer/agents/django-reviewer.md`.

## Changing a plugin

1. Edit the canonical catalog or `skills/<id>/` tree.
2. Run `python scripts/generate_adapters.py`.
3. Review all generated changes.
4. Run the validation commands below.

Generated adapters must stay package-local: no symlinks, absolute paths,
parent-directory traversal, or references to another package.

## Required validation

```bash
python scripts/generate_adapters.py --check
python scripts/validate_plugins.py
python -m unittest discover -s tests -p 'test_*.py'
python scripts/smoke_plugins.py --target claude
python scripts/smoke_plugins.py --target codex
python scripts/smoke_plugins.py --target cursor
python scripts/smoke_plugins.py --target opencode
python scripts/smoke_plugins.py --target agent-skills
```

When installed, host CLIs may add extra validation, but their absence may not
skip the offline contract suite. Never point smoke tests at a real user home.

## Distribution policy

Repository changes prepare local and Git-based distribution only. Do not
publish to an external registry, authenticate a marketplace, or change a
user's host configuration as part of validation.
