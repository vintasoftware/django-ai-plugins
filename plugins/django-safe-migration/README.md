# Django Safe Migration Plugin

A Skill for writing, reviewing, and rewriting Django migrations for PostgreSQL with zero-downtime deployment safety in mind.

## What this skill covers

- Reviewing generated SQL with `sqlmigrate` before judging migration safety
- Rewriting unsafe operations with PostgreSQL-aware patterns
- Using `SeparateDatabaseAndState` splits for rolling deploy compatibility
- Creating indexes with `AddIndexConcurrently`
- Adding constraints with `NOT VALID` plus `VALIDATE`
- Handling `db_default`, `lock_timeout`, and `RunPython` risks

## Plugin structure

```text
django-safe-migration/
├── .codex-plugin/plugin.json
├── skills/django-safe-migration/SKILL.md
└── skills/django-safe-migration/references/
    ├── examples.md
    ├── operation-guide.md
    └── postgres-locks.md
```
