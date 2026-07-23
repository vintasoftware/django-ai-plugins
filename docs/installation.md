# Installation and lifecycle

Choose exactly one installation channel for each skill ID. Installing the same
ID through a native marketplace and a generic skills directory can create a
duplicate; remove the shadow copy and retain the channel recommended below.

Replace `django-expert` in the examples with any catalog ID:
`django-celery-expert`, `cdrf-expert`, `django-safe-migration`, or
`django-reviewer`.

## Migrating from flat 1.0 packages

Earlier package checkouts exposed these skills at a flat
`plugins/<id>/skills/SKILL.md` path. The normalized package layout moves each
skill into its own named directory:

| ID | Former path | Current path |
| --- | --- | --- |
| `django-expert` | `plugins/django-expert/skills/SKILL.md` | `plugins/django-expert/skills/django-expert/SKILL.md` |
| `django-celery-expert` | `plugins/django-celery-expert/skills/SKILL.md` | `plugins/django-celery-expert/skills/django-celery-expert/SKILL.md` |
| `cdrf-expert` | `plugins/cdrf-expert/skills/SKILL.md` | `plugins/cdrf-expert/skills/cdrf-expert/SKILL.md` |

If you copy packages directly, replace the complete package directory so its
skill references move with it. Do not retain both the former and current
discoverable paths: hosts can register the same skill ID twice. Native
marketplace installations should use the host-specific update steps below.

## Claude Code

Claude uses `.claude-plugin/marketplace.json`.

```text
/plugin marketplace add vintasoftware/django-ai-plugins
/plugin install django-expert@django-ai-plugins
```

Update and uninstall with Claude's plugin lifecycle:

```text
/plugin update django-expert@django-ai-plugins
/plugin uninstall django-expert@django-ai-plugins
```

Restart Claude after an update so its cache loads the new package version.

## Codex

Codex uses `.agents/plugins/marketplace.json`.

```bash
codex plugin marketplace add vintasoftware/django-ai-plugins
codex plugin add django-expert@vinta-django-ai-plugin
```

Refresh the Git snapshot before updating an installed plugin:

```bash
codex plugin marketplace upgrade vinta-django-ai-plugin
codex plugin remove django-expert@vinta-django-ai-plugin
codex plugin add django-expert@vinta-django-ai-plugin
```

Uninstall with:

```bash
codex plugin remove django-expert@vinta-django-ai-plugin
```

For local development, replace the repository slug in `marketplace add` with
the checkout path. Use an isolated Codex profile when testing; do not change a
real user's configuration.

## Cursor

Cursor uses `.cursor-plugin/marketplace.json` and package-local generated skill
copies. In Cursor Agent chat, add a local checkout or the GitHub repository:

```text
/add-plugin ./plugins/django-expert
```

For a marketplace-backed install, search for the configured team marketplace
entry and select the plugin ID. To update, refresh the marketplace and
reinstall the plugin after its version changes. To uninstall, remove it from
Cursor's Installed Plugins view. Reload the Cursor window after either action
to clear its plugin cache.

## OpenCode

OpenCode automatically loads `.opencode/plugins/django-ai-skills.js` from a
checkout. The dependency-free adapter registers only the root `skills/` path.
Keep `.opencode/`, `package.json`, and `skills/` at their repository-relative
locations.

To update, pull or replace the checkout and restart OpenCode. To uninstall,
remove the checkout or remove the copied adapter and skills together. Do not
also copy these IDs into `.opencode/skills/` or `.agents/skills/`.

OpenCode skill permissions can be configured in `opencode.json`. If a skill is
hidden or denied, allow its ID under the `permission.skill` rules; this project
does not bypass host permissions.

## Generic Agent Skills

Agent Skills consumers can read `skills/<id>/SKILL.md` directly. For a
user-level installation, copy one complete canonical directory:

```bash
cp -R skills/django-expert ~/.agents/skills/django-expert
```

Update by replacing that one directory; uninstall by removing it. Preserve
references and assets inside the skill directory. Check the target host's
permission model before granting a skill access to tools.

## Cache, duplicate, and permission troubleshooting

- If an update still shows old behavior, refresh the marketplace or checkout,
  confirm the catalog version changed, then restart the host to clear its cache.
- If an ID appears twice, list its provenance and keep only one of the native
  marketplace, OpenCode adapter, or direct Agent Skills installation.
- If discovery succeeds but invocation is denied, inspect the host's skill or
  plugin permission settings. The adapters never relax permissions.
- Run `python scripts/smoke_plugins.py --target <host>` from the checkout to
  verify the package without modifying a real home directory.
