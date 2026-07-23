# Compatibility matrix

The offline contract suite is mandatory for every host. A live host check is
additional evidence, not a replacement for deterministic package validation.

| Host | Recommended channel | Delivered surface | Current verification |
| --- | --- | --- | --- |
| Claude Code | Claude marketplace | Skill for four packages; Claude agent for `django-reviewer` | Isolated structural smoke plus `claude plugin validate` |
| Codex | `.agents/plugins` marketplace | Package-local portable skill | Isolated structural install, update, uninstall, and discovery |
| Cursor | Cursor marketplace or `/add-plugin` | Package-local generated skill via explicit manifest path | Official-schema contract and isolated structural discovery; live Cursor Agent unavailable in the maintainer environment |
| OpenCode | Repository-local `.opencode` adapter | Canonical root `skills/` path | Adapter imported from a copied checkout with Node; local OpenCode CLI unavailable because its own postinstall is incomplete |
| Agent Skills clients | Direct `skills/<id>/` copy | Canonical portable skill | Frontmatter, reference, path, and isolated discovery validation |

## Behavioral parity

The canonical skill body is identical across portable hosts. Claude's
`django-reviewer` adds only host-specific agent metadata; its generated body is
checked against the canonical reviewer skill. Generated package projections
are physical copies, not symlinks, so marketplace packages remain
self-contained.

## Support boundary

The repository prepares manifests and Git-based install surfaces. It does not
publish to Claude, Cursor, npm, or another external registry. Host release
changes can require a schema refresh; update the compatibility tests before
changing an adapter contract.
