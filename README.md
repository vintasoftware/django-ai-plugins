# Django AI Skills

Portable Django expertise for Claude Code, Codex, Cursor, OpenCode, and tools
that implement the [Agent Skills specification](https://agentskills.io/).

The repository has one canonical authoring tree under `skills/`. Host manifests
and package-local projections are generated from `plugins/catalog.json`, so the
same behavior is delivered without maintaining separate copies by hand.

## Included capabilities

| ID | Capability |
| --- | --- |
| `django-expert` | Django backend, ORM, DRF, security, testing, and performance guidance |
| `django-celery-expert` | Reliable Celery task design, retries, scheduling, and operations |
| `cdrf-expert` | DRF class selection, lifecycle tracing, MRO, and safe override guidance |
| `django-safe-migration` | PostgreSQL-aware, zero-downtime Django migration guidance |
| `django-reviewer` | Report-first Django and Python review for recent or user-selected changes |

See [installation and lifecycle instructions](docs/installation.md) for each
host and the [compatibility matrix](docs/compatibility.md) for the validation
level of every adapter.

## Repository layout

```text
skills/                         canonical Agent Skills
plugins/catalog.json            canonical metadata and host declarations
plugins/<id>/                   self-contained generated plugin packages
.claude-plugin/                 Claude marketplace
.agents/plugins/                Codex marketplace
.cursor-plugin/                 Cursor marketplace
.opencode/plugins/              OpenCode skills-path adapter
scripts/                        generation, validation, and isolated smoke checks
```

Package manifests and package-local skills are generated outputs. Contributors
should read [AGENTS.md](AGENTS.md) before changing the catalog or skill content.

## Local validation

```bash
python scripts/generate_adapters.py --check
python scripts/validate_plugins.py
python -m unittest discover -s tests -p 'test_*.py'
```

The smoke runner accepts `claude`, `codex`, `cursor`, `opencode`, and
`agent-skills` targets and always installs into a temporary location:

```bash
python scripts/smoke_plugins.py --target cursor
```

These skills can complement the
[django-ai-boost MCP server](https://github.com/vintasoftware/django-ai-boost);
neither project requires the other.

## License

MIT © Vinta Software
