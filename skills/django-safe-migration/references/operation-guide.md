# Operation Guide — Zero Downtime Migrations

Each entry explains: what PostgreSQL does, which lock it takes, what that lock blocks, and the safe alternative.

> **PostgreSQL version assumptions**: This guide assumes PostgreSQL 11 or later for `ADD COLUMN` behavior (constant defaults no longer rewrite the table). It assumes PostgreSQL 12 or later for the `SET NOT NULL` + CHECK optimization (scan is skipped when a valid `CHECK IS NOT NULL` exists). On earlier versions, both operations perform full table rewrites and should be treated as unsafe on large tables.

> **Docs links**: if the project has a docs/wiki URL configured in `SKILL.md`, append it when flagging each operation in review output. If none is configured, omit links.

## Table of Contents

- [ADD COLUMN](#add-column)
- [SET NOT NULL on Existing Nullable Column](#set-not-null-on-existing-nullable-column)
- [DROP COLUMN](#drop-column)
- [DROP TABLE](#drop-table)
- [RENAME COLUMN](#rename-column)
- [RENAME TABLE](#rename-table)
- [ALTER COLUMN TYPE](#alter-column-type)
- [CREATE INDEX](#create-index)
- [DROP INDEX](#drop-index)
- [ADD UNIQUE CONSTRAINT](#add-unique-constraint)
- [ADD FOREIGN KEY CONSTRAINT](#add-foreign-key-constraint)
- [ADD CHECK CONSTRAINT](#add-check-constraint)
- [ADD EXCLUSION CONSTRAINT](#add-exclusion-constraint)
- [RunPython — Data Migrations](#runpython--data-migrations)
- [RunSQL](#runsql)
- [Quick Lock Reference](#quick-lock-reference)

---

## ADD COLUMN

### Why it can be unsafe

`ALTER TABLE ADD COLUMN` takes `ACCESS EXCLUSIVE` briefly. For PostgreSQL 11+, adding a column with a constant default no longer rewrites the table — it's a metadata-only operation. The lock is held only for milliseconds.

However, if the column is `NOT NULL` with no database-level default, old code (still running during rolling deploy) will try to INSERT rows without specifying the new column — and the DB will reject them with `column cannot be null`.

### With `db_default` — Safe ✅

Django 5.0+ `db_default` sets the default at the database level. The DB fills in the value for any INSERT that omits the column, so old code continues to work.

```python
field = models.CharField(max_length=100, db_default="")
field = models.BooleanField(db_default=False)
field = models.IntegerField(db_default=0)
```

One migration file. No split needed.

### Nullable — Safe ✅

```python
field = models.CharField(max_length=100, null=True, blank=True)
```

Old code omitting the column gets NULL — no constraint violation.

### With Django `default` only, NOT NULL — Partially Unsafe ⚠️

The custom backend runs `ADD COLUMN DEFAULT … NOT NULL` then `DROP DEFAULT`. The DDL itself is safe (no table rewrite). But after the migration, the database default is gone. Old code inserts that omit the column will fail with `column cannot be null` until all instances are restarted.

**Prefer `db_default`** to keep the default at the DB level and eliminate this window.

---

## SET NOT NULL on Existing Nullable Column

### Why it's unsafe

`ALTER TABLE ALTER COLUMN SET NOT NULL` scans every row in the table to verify no NULLs exist. On a large table this takes minutes under `ACCESS EXCLUSIVE`, blocking all reads and writes.

### Safe: four-step CHECK CONSTRAINT path ✅

PostgreSQL 12+ skips the full scan for `SET NOT NULL` if a valid `CHECK (col IS NOT NULL)` constraint already exists. The strategy: add the check as `NOT VALID` (fast), validate it separately (slow but non-blocking), then `SET NOT NULL` (fast, skips scan).

**Migration 1** — add CHECK NOT VALID (fast, `ACCESS EXCLUSIVE` on metadata only):
```sql
ALTER TABLE app_model ADD CONSTRAINT chk_col_not_null CHECK (col IS NOT NULL) NOT VALID;
```

**Migration 2** — validate (`SHARE UPDATE EXCLUSIVE`, non-blocking, long-running, `atomic = False`):
```sql
ALTER TABLE app_model VALIDATE CONSTRAINT chk_col_not_null;
```

**Migration 3** — apply NOT NULL + drop CHECK (fast, no scan because valid CHECK exists):
```sql
ALTER TABLE app_model ALTER COLUMN col SET NOT NULL;
ALTER TABLE app_model DROP CONSTRAINT chk_col_not_null;
```

---

## DROP COLUMN

### Why it can be unsafe

`ALTER TABLE DROP COLUMN` itself is fast (metadata + `ACCESS EXCLUSIVE` briefly). The problem is **code compatibility**: Django generates explicit column lists in every `SELECT`. If the column is dropped before all instances restart with the new code, old code will crash querying a column that no longer exists.

### Safe: two-file SeparateDatabaseAndState split ✅

**Migration 1** — remove from Django's ORM state only, no DB change (ships with code):
```python
operations = [
    migrations.SeparateDatabaseAndState(
        state_operations=[
            migrations.RemoveField(model_name="mymodel", name="myfield"),
        ],
        database_operations=[],
    )
]
```

After this migration + full deploy, old code is gone. The column still exists in the DB — nothing breaks.

**Migration 2** — drop from DB (follow-up PR):
```python
operations = [
    migrations.SeparateDatabaseAndState(
        state_operations=[],
        database_operations=[
            migrations.RunSQL(
                sql="""
                    SET LOCAL lock_timeout = '2s';
                    ALTER TABLE app_mymodel DROP COLUMN myfield;
                """,
                reverse_sql=migrations.RunSQL.noop,
            )
        ],
    )
]
```

> Deployment: Migration 1 ships with the code change. Migration 2 ships in a follow-up PR after the deploy is confirmed stable.

---

## DROP TABLE

Same reasoning and same two-file split as DROP COLUMN. First migration: `DeleteModel` in `state_operations`, empty `database_operations`. Second migration: `RunSQL DROP TABLE`.

---

## RENAME COLUMN

### Why it's unsafe

`ALTER TABLE RENAME COLUMN` is fast (metadata only), but it's a **compatibility break**: old code queries the old column name, new code queries the new name. During a rolling deploy, both versions run simultaneously — one of them will fail.

The custom backend raises `UnsafeDatabaseOperationException` to prevent this.

### Safe: three-phase multi-deployment approach ✅

There is no single-migration safe rename. The pattern:

1. **Phase 1** (current PR): Add new column (nullable or with `db_default`). Deploy code that writes to **both** old and new columns and reads from the new one with a fallback.
2. **Phase 2** (next PR): `RunPython` data migration to backfill existing rows from old → new column.
3. **Phase 3** (follow-up PR): Drop old column using the two-file `SeparateDatabaseAndState` split.

---

## RENAME TABLE

### Why it's unsafe

Same compatibility issue as RENAME COLUMN but at table level. Old code references the old table name.

The custom backend raises for `RenameModel`.

### Safe: SeparateDatabaseAndState with updatable view ✅

1. **Phase 1**: Rename the table in DB, create an [updatable view](https://www.postgresql.org/docs/current/sql-createview.html#SQL-CREATEVIEW-UPDATABLE-VIEWS) with the old name. Old code reads/writes through the view. New code uses the real table.
2. **Phase 2**: After full deployment, drop the view.

---

## ALTER COLUMN TYPE

### Why it's unsafe

`ALTER TABLE ALTER COLUMN TYPE` acquires `ACCESS EXCLUSIVE`. If the type change requires rewriting existing values (e.g., varchar → integer), PostgreSQL rewrites the entire table — potentially minutes of lock on large tables. Even for "cheap" casts, the lock is held.

The custom backend raises for all type changes.

### PostgreSQL-safe type changes (but still blocked by the backend)

These three casts are free in PostgreSQL — no table rewrite, just a metadata update:

1. `varchar(N)` → `varchar(M)` where M > N (widening)
2. `varchar(N)` → `text`
3. `numeric(P, S)` → `numeric(P2, S)` where P2 > P (precision increase)

For these, bypass the backend guard using `SeparateDatabaseAndState` with `RunSQL`:

```python
operations = [
    migrations.SeparateDatabaseAndState(
        state_operations=[
            migrations.AlterField(
                model_name="mymodel",
                name="myfield",
                field=models.TextField(),
            ),
        ],
        database_operations=[
            migrations.RunSQL(
                sql="ALTER TABLE app_mymodel ALTER COLUMN myfield TYPE text;",
                reverse_sql="ALTER TABLE app_mymodel ALTER COLUMN myfield TYPE varchar(100);",
            )
        ],
    )
]
```

### Structurally unsafe type changes

For anything requiring a value rewrite (e.g., varchar → integer, changing semantics), use the same three-phase approach as column rename: add new column → backfill → drop old column.

---

## CREATE INDEX

### Why it's unsafe

`CREATE INDEX` (non-concurrent) takes a `SHARE` lock for the entire duration of the index build. On a large table this can take minutes, blocking all writes.

### Safe: `AddIndexConcurrently` ✅

`CREATE INDEX CONCURRENTLY` takes `SHARE UPDATE EXCLUSIVE` — doesn't block reads or writes. Requires `atomic = False` because it cannot run inside a transaction.

```python
from django.contrib.postgres.operations import AddIndexConcurrently

class Migration(migrations.Migration):
    atomic = False  # required — CONCURRENTLY cannot run in a transaction

    operations = [
        AddIndexConcurrently(
            model_name="mymodel",
            index=models.Index(fields=["myfield"], name="mymodel_myfield_idx"),
        ),
    ]
```

---

## DROP INDEX

### Why it can be unsafe

`DROP INDEX` (non-concurrent) takes `ACCESS EXCLUSIVE`, briefly blocking reads and writes.

### Safe: `RemoveIndexConcurrently` ✅

```python
from django.contrib.postgres.operations import RemoveIndexConcurrently

class Migration(migrations.Migration):
    atomic = False

    operations = [
        RemoveIndexConcurrently(
            model_name="mymodel",
            name="mymodel_myfield_idx",
        ),
    ]
```

---

## ADD UNIQUE CONSTRAINT

### Why it's unsafe

Django's default approach runs `CREATE INDEX` inline (takes `SHARE` lock, blocks writes during build) then promotes it to a constraint. On a large table this is equivalent to a slow `CREATE INDEX`.

The custom backend's `alter_field` already handles the index-first pattern for `unique=True` field changes — but `AddConstraint(UniqueConstraint(...))` on an existing field does not get this treatment automatically.

> Note: `NOT VALID` is not available for UNIQUE constraints — it is only supported for FOREIGN KEY and CHECK constraints (PostgreSQL 15: [sql-altertable.html](https://www.postgresql.org/docs/15/sql-altertable.html)).

### Safe: index first, then promote ✅

**Migration 1** — create the index concurrently:
```python
class Migration(migrations.Migration):
    atomic = False

    operations = [
        AddIndexConcurrently(
            model_name="mymodel",
            index=models.Index(fields=["myfield"], name="mymodel_myfield_uniq"),
        ),
    ]
```

**Migration 2** — promote the index to a constraint (fast, uses existing index):
```python
operations = [
    migrations.SeparateDatabaseAndState(
        state_operations=[
            migrations.AlterField(
                model_name="mymodel",
                name="myfield",
                field=models.CharField(max_length=100, unique=True),
            ),
        ],
        database_operations=[
            migrations.RunSQL(
                sql="ALTER TABLE app_mymodel ADD CONSTRAINT mymodel_myfield_uniq UNIQUE USING INDEX mymodel_myfield_uniq;",
                reverse_sql="ALTER TABLE app_mymodel DROP CONSTRAINT mymodel_myfield_uniq;",
            )
        ],
    )
]
```

---

## ADD FOREIGN KEY CONSTRAINT

### Why it's unsafe

`ALTER TABLE ADD CONSTRAINT FOREIGN KEY` scans the entire child table to validate referential integrity. It takes `SHARE ROW EXCLUSIVE` on the child table **and** `SHARE ROW EXCLUSIVE` on the referenced table simultaneously. This blocks writes (but not reads) on both tables for the duration of the scan — on large tables that is minutes.

> ⚠️ **DROP CONSTRAINT on a FK** acquires `ACCESS EXCLUSIVE` on **both** the child table and the referenced table. PostgreSQL implements FK constraints as system triggers on both sides; dropping the constraint removes those triggers. A migration that drops and immediately re-adds a FK (Django's default when altering a FK field) will hold `ACCESS EXCLUSIVE` on both tables for the full duration of the re-add scan if `NOT VALID` is not used. Always include `SET LOCAL lock_timeout` before any `DROP CONSTRAINT` on a FK.

### Safe: NOT VALID + VALIDATE pattern ✅

`NOT VALID` skips the scan of existing rows — only new/updated rows are checked going forward. `VALIDATE CONSTRAINT` then validates existing rows under `SHARE UPDATE EXCLUSIVE` (non-blocking).

**Migration 1** — add as NOT VALID (`SHARE ROW EXCLUSIVE` on both tables — no row scan, lock held milliseconds):
```python
operations = [
    migrations.SeparateDatabaseAndState(
        state_operations=[
            migrations.AddField(
                model_name="mymodel",
                name="other",
                field=models.ForeignKey(
                    "otherapp.OtherModel",
                    null=True,
                    blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                ),
            ),
        ],
        database_operations=[
            migrations.RunSQL(
                sql="""
                    SET LOCAL lock_timeout = '2s';
                    ALTER TABLE app_mymodel ADD COLUMN other_id integer NULL;
                    ALTER TABLE app_mymodel
                        ADD CONSTRAINT app_mymodel_other_id_fk
                        FOREIGN KEY (other_id) REFERENCES otherapp_othermodel(id)
                        NOT VALID;
                """,
                reverse_sql="""
                    SET LOCAL lock_timeout = '2s';
                    ALTER TABLE app_mymodel DROP CONSTRAINT app_mymodel_other_id_fk;
                    ALTER TABLE app_mymodel DROP COLUMN other_id;
                """,
            )
        ],
    )
]
```

`SET LOCAL lock_timeout` scopes the timeout to this transaction so the migration fails fast (with a clear error) instead of waiting indefinitely and cascading into connection pool exhaustion. `2s` is the default; adjust if the table is known to have long-running transactions. `SET LOCAL` is used here (not `SET`) because Migration 1 runs inside a normal Django transaction — `SET LOCAL` resets automatically when the transaction commits.

The `reverse_sql` also includes `SET LOCAL lock_timeout` because `DROP CONSTRAINT` on a FK takes `ACCESS EXCLUSIVE` on both the child and referenced table.

Do **not** add `lock_timeout` to the `VALIDATE CONSTRAINT` step. `VALIDATE` uses `SHARE UPDATE EXCLUSIVE` (non-blocking), is expected to run for a long time while scanning rows, and would cause spurious failures if a lock_timeout fired during the scan.

**Migration 2** — validate (`SHARE UPDATE EXCLUSIVE` on child table + `ROW SHARE` on referenced table — both non-blocking, `atomic = False`):
```python
class Migration(migrations.Migration):
    atomic = False

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE app_mymodel VALIDATE CONSTRAINT app_mymodel_other_id_fk;",
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
```

> Deployment: Migration 1 ships with the code change. Migration 2 ships in a follow-up PR.

### Why `atomic = False` for VALIDATE CONSTRAINT

Three reasons — not just "it's long-running":

1. **`SHARE UPDATE EXCLUSIVE` is self-conflicting** (see the lock conflict matrix in `postgres-locks.md`, the `SHARE UPDATE EXCLUSIVE` row × `SHARE UPDATE EXCLUSIVE` column = X). A session already holding `SHARE UPDATE EXCLUSIVE` on a table conflicts with another session trying to acquire it; running inside a wrapping transaction that already holds other locks increases the window for this conflict.
2. **Accumulated lock hold time**: with `atomic = True`, Django wraps all operations in a single `BEGIN…COMMIT`. The `VALIDATE` scan runs inside that transaction, holding all prior statement locks until the scan completes — potentially minutes. Other sessions waiting on those earlier locks pile up.
3. **Clean release on completion**: with `atomic = False`, `VALIDATE` runs in its own transaction and releases its `SHARE UPDATE EXCLUSIVE` + `ROW SHARE` locks immediately on completion. The next statement starts with a clean lock slate.

### Django and DEFERRABLE INITIALLY DEFERRED

Django generates all FK constraints on PostgreSQL as `DEFERRABLE INITIALLY DEFERRED`. If a migration drops a FK in the same transaction as DML operations that triggered the deferred FK trigger, PostgreSQL will raise:

```
ERROR: cannot ALTER TABLE because it has pending trigger events
```

Django's generated workaround is:

```sql
SET CONSTRAINTS '<constraint_name>' IMMEDIATE;
```

placed immediately before the `DROP CONSTRAINT`. This forces the pending deferred trigger to fire immediately and be resolved before the DROP. This line is safe and expected — do not remove it from reviewed migrations.

---

## ADD CHECK CONSTRAINT

### Why it's unsafe

Same as FK: `ALTER TABLE ADD CONSTRAINT CHECK` scans every row under `ACCESS EXCLUSIVE`.

### Safe: NOT VALID + VALIDATE ✅

```python
# Migration 1: add as NOT VALID (fast, ACCESS EXCLUSIVE on metadata only)
# SET LOCAL scopes lock_timeout to this transaction; omit from VALIDATE step (SHARE UPDATE EXCLUSIVE, non-blocking)
migrations.RunSQL(
    sql="""
        SET LOCAL lock_timeout = '2s';
        ALTER TABLE app_mymodel ADD CONSTRAINT chk_myfield CHECK (myfield > 0) NOT VALID;
    """,
    reverse_sql="""
        SET LOCAL lock_timeout = '2s';
        ALTER TABLE app_mymodel DROP CONSTRAINT chk_myfield;
    """,
)

# Migration 2: validate (atomic = False, non-blocking)
class Migration(migrations.Migration):
    atomic = False
    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE app_mymodel VALIDATE CONSTRAINT chk_myfield;",
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
```

---

## ADD EXCLUSION CONSTRAINT

### Why it's unsafe

`ALTER TABLE ADD CONSTRAINT EXCLUDE` builds a GiST or SP-GiST index inline under `ACCESS EXCLUSIVE`. There is no `CONCURRENTLY` variant for exclusion constraints.

The custom backend raises for `ExclusionConstraint`. No in-place safe alternative exists — requires downtime window or new table + copy.

> Note: `NOT VALID` is not available for EXCLUDE constraints — it is only supported for FOREIGN KEY and CHECK constraints (PostgreSQL 15: [sql-altertable.html](https://www.postgresql.org/docs/15/sql-altertable.html)).

---

## RunPython — Data Migrations

### Required rules

**1. Always use `apps.get_model`, never direct imports.**

Why: a direct import uses the *current* model class. In a migration, you need the model as it existed *at the time the migration was written*. If the model later changes (field added, renamed), a direct import in an old migration will fail or corrupt data.

```python
# Wrong — uses current model, breaks if schema changes later
from myapp.models import MyModel

# Correct — uses historical model snapshot
def migrate(apps, schema_editor):
    MyModel = apps.get_model("myapp", "MyModel")
```

**2. Always provide `reverse_code`.**

```python
migrations.RunPython(migrate, reverse_code=migrations.RunPython.noop)
```

**3. Batch large updates.**

A single `.update()` on millions of rows holds `FOR NO KEY UPDATE` row locks on every matching row for the full duration of the transaction, blocking application writes on those rows. Use chunked updates instead:

```python
def migrate(apps, schema_editor):
    MyModel = apps.get_model("myapp", "MyModel")
    batch_size = 1000
    while True:
        batch_ids = list(
            MyModel.objects
            .filter(status__isnull=True)[:batch_size]
            .values_list("pk", flat=True)
        )
        if not batch_ids:
            break
        MyModel.objects.filter(pk__in=batch_ids).update(status="active")
```

Each batch runs in its own short write-lock window (when the migration has `atomic = False`) or commits row locks more frequently, keeping the lock window small per batch and avoiding long queues on application writes.

---

## RunSQL

**Always provide `reverse_sql`.** If the operation is truly irreversible, use `migrations.RunSQL.noop` and add a comment explaining why.

For DDL statements that are long-running or use `CONCURRENTLY`, set `atomic = False` on the `Migration` class.

---

## Quick Lock Reference

| Operation | Lock | Blocks | Safe? |
|---|---|---|---|
| `ADD COLUMN` (constant or no default) | `ACCESS EXCLUSIVE` (metadata only) | briefly | ✅ |
| `ADD COLUMN NOT NULL` no `db_default` | `ACCESS EXCLUSIVE` (metadata only) | briefly | ⚠️ old inserts fail |
| `DROP COLUMN` | `ACCESS EXCLUSIVE` (metadata only) | briefly | ⚠️ old code breaks |
| `SET NOT NULL` (no CHECK constraint) | `ACCESS EXCLUSIVE` (full scan) | reads + writes | ❌ |
| `SET NOT NULL` (with valid CHECK) | `ACCESS EXCLUSIVE` (metadata only) | briefly | ✅ |
| `ALTER COLUMN TYPE` (safe cast) | `ACCESS EXCLUSIVE` (metadata only) | briefly | ✅ via RunSQL |
| `ALTER COLUMN TYPE` (rewrite) | `ACCESS EXCLUSIVE` (full rewrite) | reads + writes | ❌ |
| `CREATE INDEX` | `SHARE` | writes | ❌ |
| `CREATE INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | nothing | ✅ |
| `DROP INDEX` | `ACCESS EXCLUSIVE` | reads + writes | ❌ |
| `DROP INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | nothing | ✅ |
| `ADD CONSTRAINT FK` (inline) | `SHARE ROW EXCLUSIVE` (full scan, child + referenced table) | writes | ❌ |
| `ADD CONSTRAINT FK NOT VALID` | `SHARE ROW EXCLUSIVE` on both tables (no row scan — lock held milliseconds) | briefly | ✅ |
| `DROP CONSTRAINT` (FK) | `ACCESS EXCLUSIVE` on child table + referenced table | reads + writes on both | ❌ |
| `VALIDATE CONSTRAINT` (FK) | `SHARE UPDATE EXCLUSIVE` (child) + `ROW SHARE` (referenced table) | nothing meaningful | ✅ |
| `ADD CONSTRAINT CHECK` (inline) | `ACCESS EXCLUSIVE` (full scan) | reads + writes | ❌ |
| `ADD CONSTRAINT UNIQUE` (inline) | `SHARE` (index build) | writes | ❌ |
| `RENAME COLUMN` | `ACCESS EXCLUSIVE` (metadata only) | briefly | ❌ code breaks |
| `RENAME TABLE` | `ACCESS EXCLUSIVE` (metadata only) | briefly | ❌ code breaks |
