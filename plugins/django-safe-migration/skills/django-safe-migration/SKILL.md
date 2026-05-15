---
name: django-safe-migration
description: >
  Write, review, and rewrite Django migrations for PostgreSQL with zero-downtime guarantees.
  Use this skill whenever the user mentions migrations, Django schema changes, or deployment safety — even if they don't say "zero downtime" explicitly.
  Trigger on: "review this migration", "is this migration safe?", "write a migration for...", "rewrite this migration", "how do I add a NOT NULL column / drop a column / add an index / rename a column / add a FK without downtime", "will this migration cause locks?", "this migration is blocking production".
  Covers: SeparateDatabaseAndState two-file splits, AddIndexConcurrently, FK NOT VALID + VALIDATE, db_default for NOT NULL columns, lock_timeout, and RunPython safety rules.
---

# Django Migration — Zero Downtime

## Project Configuration

Read the project's `CLAUDE.md` or `AGENTS.md` for the values below. If they are not set, use the defaults shown.

| Key | Default | Notes |
|---|---|---|
| **Django version** | unknown | Affects `db_default` availability — only Django 5.0+ supports it |
| **Deploy strategy** | rolling deploy | Rolling deploy is the most restrictive; blue/green or maintenance-window deploys allow more operations |
| **Runtime guard** | none | If a guard is configured (e.g. `django-pg-zero-downtime-migrations`), operations it blocks are **Errors**; uncovered operations are **Warnings** |
| **Migration command** | `python manage.py sqlmigrate` | e.g. `make sqlmigrate` or `docker compose run web python manage.py sqlmigrate` |
| **Docs / wiki URL** | none | If set, append `#<anchor>` links when flagging issues in review output |

To configure this skill for your project, add a section like this to your `CLAUDE.md` or `AGENTS.md`:

```
## django-safe-migration
- Django version: 5.1
- Deploy strategy: rolling deploy
- Runtime guard: none
- Migration command: docker compose run web python manage.py sqlmigrate
- Docs URL: https://github.com/your-org/repo/wiki/migrations
```

---

## When to Use

- "Review this migration"
- "Is this migration safe?"
- "Write a migration for..."
- "Rewrite this migration to be safe"
- "How do I add a NOT NULL column / drop a column / add an index / rename a column / add a FK..."

---

## Why Zero-Downtime Migrations Matter

In a rolling deploy, the new database schema is applied first, then application instances are restarted one by one. At any moment during the deploy, old code and new code run simultaneously against the same database.

Every migration must be safe to run while the previous version of the app is still serving traffic. A migration that takes an `ACCESS EXCLUSIVE` lock on a large table blocks all reads and writes — downtime even for a few seconds on a busy table.

The problem is not just the lock itself but the **wait queue**: a fast `ALTER TABLE` that takes 50ms will queue behind any long-running transaction, and all subsequent queries queue behind the migration. On a busy table this cascades into connection pool exhaustion.

---

## How PostgreSQL Locking Works

| Lock | Acquired by | Blocks |
|---|---|---|
| `ACCESS EXCLUSIVE` | Most `ALTER TABLE`, `DROP INDEX`, `DROP CONSTRAINT` (FK) | All reads and writes |
| `SHARE ROW EXCLUSIVE` | `ADD FOREIGN KEY` (on child table + referenced table simultaneously) | Writes only (on both tables) |
| `SHARE` | `CREATE INDEX` | Writes only |
| `SHARE UPDATE EXCLUSIVE` | `CREATE INDEX CONCURRENTLY`, `VALIDATE CONSTRAINT` | Nothing meaningful — safe under traffic |

For the full conflict matrix (table-level locks × business logic operations × row-level locks) and the FIFO wait-queue explanation, load `references/postgres-locks.md`. Load it when:
- explaining *why* a specific operation is unsafe
- a developer asks what a lock type blocks or conflicts with
- reasoning about whether two concurrent operations interact

---

## lock_timeout

Any operation that requires `ACCESS EXCLUSIVE` should be preceded by `SET LOCAL lock_timeout`. This causes the migration to fail fast (with a clear error) instead of waiting indefinitely for the lock — preventing connection pool exhaustion from queue cascading.

For a normal transactional migration:

```python
migrations.RunSQL("SET LOCAL lock_timeout = '2s'"),
migrations.AlterField(...),  # or any ACCESS EXCLUSIVE operation
```

`SET LOCAL` scopes the timeout to the current transaction, so it does not affect other sessions or persist after the migration completes.

**Default**: `2s` — adjust up if the table is known to have long-running transactions that legitimately need more time, or down for stricter environments.

For `atomic = False` migrations, combine `SET LOCAL` and the DDL in the same `RunSQL` operation; see Structural Rules below.

---

## Key Patterns

### NOT VALID + VALIDATE (for FK and CHECK constraints)

A two-step PostgreSQL technique to add a constraint without a long lock:

1. **`ADD CONSTRAINT … NOT VALID`** — creates the constraint and enforces it on new writes immediately, but skips scanning existing rows. Takes a brief lock with no table scan — `SHARE ROW EXCLUSIVE` on both tables for FK constraints, `ACCESS EXCLUSIVE` for CHECK constraints.
2. **`VALIDATE CONSTRAINT`** — scans existing rows to confirm they satisfy the constraint. Takes `SHARE UPDATE EXCLUSIVE` (plus `ROW SHARE` on the referenced table for FK constraints), which does not block reads or writes.

The dangerous part is the full-table scan, not the constraint creation itself. Splitting it keeps the write-blocking lock window to milliseconds, with the long scan moved to a non-blocking step.

PostgreSQL docs: [`NOT VALID`](https://www.postgresql.org/docs/current/sql-altertable.html#SQL-ALTERTABLE-DESC-ADD-TABLE-CONSTRAINT) · [`VALIDATE CONSTRAINT`](https://www.postgresql.org/docs/current/sql-altertable.html#SQL-ALTERTABLE-DESC-VALIDATE-CONSTRAINT)

---

## Runtime Guards

Some projects configure a custom database backend or linter that raises errors for unsafe operations at migration time (e.g. `zero_downtime_migrations`, `django-pg-zero-downtime-migrations`, `django-migration-linter`).

When reviewing a migration:
- Operations the project's runtime guard **blocks** → classify as **Error** (migration will not run)
- Operations the guard **does not cover** → classify as **Warning** (migration runs but may cause downtime)

If no runtime guard is configured, treat all unsafe operations as **Errors** that require a safe rewrite before deploying to production.

Check the Project Configuration block above (or `AGENTS.md`) for what this project's guard covers.

---

## Mode 1: Review

### Goal
Identify every operation that is unsafe or risky for a rolling deploy on PostgreSQL.

### Steps

1. Read the migration file in full.
2. Run `<migration_command> <app_label> <migration_name>` to get the actual SQL Django will execute. **Always do this — the generated SQL is the ground truth.** Use the `Migration command` value from `CLAUDE.md`/`AGENTS.md`; default is `python manage.py sqlmigrate`. If the key is not set and a `Makefile` or `docker-compose.yml` exists in the project root, ask the user: "How do you run sqlmigrate in this project?" and suggest they save the answer to `CLAUDE.md`. The ORM operation class alone is not sufficient: for example, `AlterField` on a FK field that adds `null=True` also drops and re-adds the FK constraint, emitting `DROP CONSTRAINT` (taking `ACCESS EXCLUSIVE` on both the child and referenced table) followed by `ADD CONSTRAINT FOREIGN KEY` without `NOT VALID` (taking `SHARE ROW EXCLUSIVE` with a full scan on both tables) — neither is visible from the migration file alone.
3. Load `references/operation-guide.md`. Load `references/postgres-locks.md` when explaining why a flagged operation is unsafe.
4. For each SQL statement produced, check it against the detection checklist below.
5. If any operation requires `ACCESS EXCLUSIVE` (flagged as error or warning), ask the user before outputting the report:
   > "This migration contains an `ACCESS EXCLUSIVE` operation. A `lock_timeout` should be added to fail fast instead of queuing and cascading. The default is `2s` — confirm or provide a custom value."
   If the migration already contains `SET LOCAL lock_timeout`, note the existing value and ask the user to confirm it is appropriate.
   Use the confirmed value in the fix instructions.
6. Output a structured report:

## Migration Review: <filename>

### Errors — will cause downtime or be blocked by runtime guard
- [ERROR] `<OperationClass>` on `<app>.<Model>.<field>`: <what it does and why it's unsafe>
  Fix: <one-sentence description of the safe alternative>
  What this rewrite changes: clarify whether `ACCESS EXCLUSIVE` is still required in the safe version, and if so, explain what actually improves — lock duration (full table scan → milliseconds), failure mode (silent queue cascade → fast timeout error), or both. Never let a reader assume the rewrite eliminates the lock entirely.
  <wiki/docs link if configured>

### Warnings — may cause extended locks or deployment issues
- [WARNING] `<OperationClass>`: <issue>
  Fix: <safe alternative>

### Structural Issues
- [ERROR|WARNING] <issue> (e.g., missing atomic=False, RunPython without reverse)

### Safe
- [OK] <operations that pass all checks>

7. If there are errors or warnings, offer to rewrite (Mode 3).
8. If everything passes, confirm the migration is safe to deploy.

---

## Mode 2: Write

### Goal
Generate correct, zero-downtime migration(s) for a described change.

### Steps

1. Load `references/operation-guide.md` and `references/examples.md`.
2. Clarify the operation if ambiguous:
   - What model and field?
   - New column or changing an existing one?
   - For FK: which table is referenced? New column or existing?
   - For type changes: from what type to what type?
   - Django version (affects `db_default` availability)?
3. If the operation will require `ACCESS EXCLUSIVE`, ask the user:
   > "This migration will use `ACCESS EXCLUSIVE`. A `lock_timeout` will be included to fail fast if the lock cannot be acquired. The default is `2s` — confirm or provide a custom value."
4. Determine how many migration files are needed — many patterns require two files in separate PRs.
5. Generate the migration file(s) using patterns from `references/examples.md`. Add `SET LOCAL lock_timeout = '<confirmed_value>'` before each `ACCESS EXCLUSIVE` statement. In normal `atomic = True` migrations, this can be a preceding `RunSQL`; in `atomic = False` migrations, combine the timeout and DDL in the same `RunSQL` operation so `SET LOCAL` is still active when the DDL runs.
6. When two files are needed, always output deployment instructions:

```
## Deployment Order
- Migration 1: ships in the same PR as the model/code change
- Migration 2: ships in a follow-up PR after the deploy is confirmed stable
```

---

## Mode 3: Rewrite

### Goal
Transform an existing unsafe migration into one or more safe migrations.

### Steps

1. Read the migration file.
2. Identify all unsafe operations using the detection checklist.
3. Load `references/operation-guide.md` and `references/examples.md`.
4. If any operation requires `ACCESS EXCLUSIVE`, ask the user:
   > "This migration contains an `ACCESS EXCLUSIVE` operation. A `lock_timeout` will be added to the rewrite to fail fast if the lock cannot be acquired. The default is `2s` — confirm or provide a custom value."
5. For each unsafe operation, apply the correct safe pattern.
6. Add `SET LOCAL lock_timeout = '<confirmed_value>'` before each `ACCESS EXCLUSIVE` statement in the rewritten migration. In normal `atomic = True` migrations, this can be a preceding `RunSQL`; in `atomic = False` migrations, combine the timeout and DDL in the same `RunSQL` operation so `SET LOCAL` is still active when the DDL runs.
7. If the rewrite requires splitting into two files, generate both and include deployment instructions.
8. Preserve: migration number prefix, `dependencies`, any safe operations unchanged.
9. After rewriting, verify structural rules (see below).
10. After the migration code, always output a **"What this rewrite changes"** block that explains:
    - Whether `ACCESS EXCLUSIVE` is still required (often yes — be explicit about this).
    - What actually improves: lock duration (full table scan → milliseconds for metadata-only ops), failure mode (silent queue → fast timeout error with `lock_timeout`), or both.
    - Any data integrity window introduced (e.g., `NOT VALID` means existing rows are unvalidated until Migration 2 runs) and whether it matters given the table's prior state.

---

## Detection Checklist

### Errors — unsafe regardless of runtime guard

| Django operation | What to detect | Why it's unsafe |
|---|---|---|
| `AddField` | `null=False` and no `db_default` (Django 5.0+) | Old code inserts omit the column — no DB-level default to fall back on |
| `RemoveField` | not inside `SeparateDatabaseAndState` | Old code queries the dropped column by name — crashes immediately |
| `DeleteModel` | not inside `SeparateDatabaseAndState` | Old code queries the dropped table — crashes immediately |
| `AddIndex` | not using `AddIndexConcurrently` | `CREATE INDEX` takes `SHARE` lock — blocks writes during build |
| `RemoveIndex` | not using `RemoveIndexConcurrently` | `DROP INDEX` takes `ACCESS EXCLUSIVE` — blocks reads and writes |
| `AddConstraint` (FK) | not using `NOT VALID + VALIDATE` pattern | Full table scan under `SHARE ROW EXCLUSIVE` on both the child and referenced table — blocks writes (not reads) for the scan duration |
| `AddConstraint` (CHECK) | not using `NOT VALID + VALIDATE` pattern | Full table scan under `ACCESS EXCLUSIVE` |
| `AlterField` | removing `null=True` on existing column without CHECK path | Full table scan under `ACCESS EXCLUSIVE` |
| `AlterField` (FK field) | `sqlmigrate` output contains `DROP CONSTRAINT` followed by `ADD CONSTRAINT FOREIGN KEY` | Django drops and re-adds the FK: `DROP CONSTRAINT` takes `ACCESS EXCLUSIVE` on both the child and referenced table; re-adding without `NOT VALID` takes `SHARE ROW EXCLUSIVE` with a full scan on both tables. Use `SeparateDatabaseAndState` with `RunSQL` to add `NOT VALID` and include `lock_timeout`. |
| `AddIndexConcurrently` or `RemoveIndexConcurrently` | `atomic` not `False` on `Migration` class | CONCURRENTLY cannot run inside a transaction — will error |
| `RunPython` | function imports model directly (`from app.models import X`) | Uses current model class, not historical snapshot — breaks old migrations |

### Additional errors if covered by the project's runtime guard

If the project has a runtime guard configured (see Project Configuration), also flag these as **Errors** (they will raise at migration time):

| Django operation | What to detect |
|---|---|
| `RenameField` | any rename |
| `RenameModel` | any rename |
| `AlterField` | column type changes |
| `AddConstraint` | `ExclusionConstraint` |

If no runtime guard is configured, flag these as **Errors** too — they require a safe rewrite.

### Warnings

| Django operation | What to detect | Issue |
|---|---|---|
| `AddConstraint` (UNIQUE) | not using index-first pattern | Inline index under `SHARE` lock — blocks writes during build |
| `AlterField` | adding `null=True` to an existing column (`DROP NOT NULL`) | Takes `ACCESS EXCLUSIVE` — fast catalog update, but queues behind any long-running transaction; all subsequent queries queue behind the migration and can exhaust the connection pool |
| `RunPython` | missing `reverse_code` | Not reversible |
| `RunSQL` | missing `reverse_sql` | Not reversible |

---

## Structural Rules (always check)

- `atomic = False` on the `Migration` class whenever any operation uses `CONCURRENTLY` or `VALIDATE CONSTRAINT`. For `VALIDATE CONSTRAINT` specifically: (1) `SHARE UPDATE EXCLUSIVE` is self-conflicting — see the conflict matrix in `references/postgres-locks.md`; (2) `atomic = True` keeps the wrapping transaction open for the full scan duration, holding all prior statement locks and increasing deadlock risk; (3) `atomic = False` lets VALIDATE run in its own transaction and release locks immediately on completion.
- `SeparateDatabaseAndState` split for `RemoveField` / `DeleteModel`: always two separate files.
- `RunPython`: always provide `reverse_code=migrations.RunPython.noop` at minimum.
- `RunSQL`: always provide `reverse_sql`. If truly irreversible, use `migrations.RunSQL.noop` and note why.
- Model access in `RunPython`: always `apps.get_model("app", "ModelName")`, never direct imports.
- `SET LOCAL lock_timeout`: required before every `ACCESS EXCLUSIVE` operation. Default value is `2s`; always confirm with the user before writing or rewriting. Use `SET LOCAL` (not `SET`) so the timeout is scoped to the current transaction.
  - **`atomic = False` exception**: `SET LOCAL` only resets at transaction end. In an `atomic = False` migration, each operation runs outside a wrapping transaction, so a standalone `migrations.RunSQL("SET LOCAL lock_timeout = '2s'")` resets before the next operation executes and has no effect. When the migration has `atomic = False`, always combine the timeout and the DDL in a single `RunSQL` call:
    ```python
    migrations.RunSQL("""
        SET LOCAL lock_timeout = '2s';
        ALTER TABLE app_model ADD COLUMN ...;
    """)
    ```
