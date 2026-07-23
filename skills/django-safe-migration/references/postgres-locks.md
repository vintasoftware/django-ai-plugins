# PostgreSQL Locking Reference

Source: [django-pg-zero-downtime-migrations](https://github.com/tbicr/django-pg-zero-downtime-migrations) and [PostgreSQL docs](https://www.postgresql.org/docs/current/explicit-locking.html).

Load this file when:
- explaining *why* a specific operation causes downtime
- a developer asks what a lock type blocks
- reasoning about whether two concurrent operations can conflict

---

## Table-Level Lock Conflict Matrix

`X` = conflict (the row lock blocks the column lock from being acquired).

|                          | `ACCESS SHARE` | `ROW SHARE` | `ROW EXCLUSIVE` | `SHARE UPDATE EXCLUSIVE` | `SHARE` | `SHARE ROW EXCLUSIVE` | `EXCLUSIVE` | `ACCESS EXCLUSIVE` |
|--------------------------|:--------------:|:-----------:|:---------------:|:------------------------:|:-------:|:---------------------:|:-----------:|:------------------:|
| `ACCESS SHARE`           |                |             |                 |                          |         |                       |             |         X          |
| `ROW SHARE`              |                |             |                 |                          |         |                       |      X      |         X          |
| `ROW EXCLUSIVE`          |                |             |                 |                          |    X    |           X           |      X      |         X          |
| `SHARE UPDATE EXCLUSIVE` |                |             |                 |            X             |    X    |           X           |      X      |         X          |
| `SHARE`                  |                |             |        X        |            X             |         |           X           |      X      |         X          |
| `SHARE ROW EXCLUSIVE`    |                |             |        X        |            X             |    X    |           X           |      X      |         X          |
| `EXCLUSIVE`              |                |      X      |        X        |            X             |    X    |           X           |      X      |         X          |
| `ACCESS EXCLUSIVE`       |       X        |      X      |        X        |            X             |    X    |           X           |      X      |         X          |

**Key insight**: `ACCESS EXCLUSIVE` conflicts with everything, including `ACCESS SHARE` (plain `SELECT`). This means any `ALTER TABLE` that holds `ACCESS EXCLUSIVE` blocks all reads and writes until it completes or is queued behind long-running transactions.

> Note: `SHARE` is not self-conflicting, so two concurrent `CREATE INDEX` (non-concurrent) operations do not block each other. However, both block all writes (`ROW EXCLUSIVE`) for their full duration.

---

## Migration Operations and Their Locks

| Lock | Migration operations |
|---|---|
| `ACCESS EXCLUSIVE` | `CREATE SEQUENCE`, `DROP SEQUENCE`, `CREATE TABLE`, `DROP TABLE`, most `ALTER TABLE` statements, `DROP INDEX`, `ALTER TABLE DROP CONSTRAINT` (FK — acquired on both child table and referenced table) |
| `SHARE ROW EXCLUSIVE` | `ALTER TABLE ADD CONSTRAINT FOREIGN KEY` (acquired on child table and referenced table simultaneously) |
| `SHARE` | `CREATE INDEX` |
| `SHARE UPDATE EXCLUSIVE` | `CREATE INDEX CONCURRENTLY`, `DROP INDEX CONCURRENTLY`, `ALTER TABLE VALIDATE CONSTRAINT` (for FK constraints, also acquires `ROW SHARE` on the referenced table) |

Notes:
- `CREATE SEQUENCE`, `DROP SEQUENCE`, `CREATE TABLE`, `DROP TABLE` take `ACCESS EXCLUSIVE` but are safe because application code should not reference them yet (new) or anymore (dropped).
- Not all `ALTER TABLE` operations take `ACCESS EXCLUSIVE` — but Django's schema editor issues them for all field/constraint changes by default. The only exceptions are operations explicitly rewritten to use `CONCURRENTLY` or `NOT VALID`, or `ADD FOREIGN KEY` which uses `SHARE ROW EXCLUSIVE` instead.
- `VALIDATE CONSTRAINT` uses `SHARE UPDATE EXCLUSIVE`, which does not conflict with reads or writes — this is why it is the safe way to validate large tables. For FK constraints, it also acquires `ROW SHARE` on the referenced table, which is likewise non-blocking.

---

## Business Logic Operations and Their Locks

| Lock | Business logic operations | Conflicts with migration lock | Conflicts with migration operations |
|---|---|---|---|
| `ACCESS SHARE` | `SELECT` | `ACCESS EXCLUSIVE` | `ALTER TABLE`, `DROP INDEX` |
| `ROW SHARE` | `SELECT FOR UPDATE` | `ACCESS EXCLUSIVE`, `EXCLUSIVE` | `ALTER TABLE`, `DROP INDEX` |
| `ROW EXCLUSIVE` | `INSERT`, `UPDATE`, `DELETE` | `ACCESS EXCLUSIVE`, `EXCLUSIVE`, `SHARE ROW EXCLUSIVE`, `SHARE` | `ALTER TABLE`, `DROP INDEX`, **`CREATE INDEX`** |

**Critical implication**: `CREATE INDEX` (non-concurrent) takes `SHARE` lock, which conflicts with `ROW EXCLUSIVE`. This means `CREATE INDEX` **blocks all writes** (`INSERT`, `UPDATE`, `DELETE`) for the entire duration of the index build — potentially minutes on a large table.

`CREATE INDEX CONCURRENTLY` takes `SHARE UPDATE EXCLUSIVE`, which does not conflict with `ROW EXCLUSIVE` — writes continue unblocked during the build.

---

## Row-Level Lock Conflict Matrix

Row locks matter for data migrations (`RunPython`) that update many rows. If migration and application code update the same rows concurrently, the second writer waits for the first to finish.

| Lock | `FOR KEY SHARE` | `FOR SHARE` | `FOR NO KEY UPDATE` | `FOR UPDATE` |
|---|:---:|:---:|:---:|:---:|
| `FOR KEY SHARE`     |   |   |   | X |
| `FOR SHARE`         |   |   | X | X |
| `FOR NO KEY UPDATE` |   | X | X | X |
| `FOR UPDATE`        | X | X | X | X |

**Implication for data migrations**: a `RunPython` that updates all rows in a large table via a single `.update()` call holds `FOR NO KEY UPDATE` row locks on every row for the duration. Application writes to those rows queue behind it. Use chunked updates or id-range batches to keep the lock window small per transaction.

---

## The FIFO Wait Queue Problem

This is why even a "fast" `ACCESS EXCLUSIVE` can cause downtime:

```
Timeline:
  [long SELECT running]        ←── holds ACCESS SHARE
  [ALTER TABLE queued]         ←── waiting for ACCESS SHARE to release, holds ACCESS EXCLUSIVE slot
  [all new queries queued]     ←── waiting behind the ALTER TABLE
```

Even if the `ALTER TABLE` itself takes 50ms, if it has to wait behind a 30-second analytics query, all new requests (including simple `SELECT`s) queue behind it for 30 seconds. On a busy service this fills the connection pool.

Four metrics to think about for any migration:

1. **Operation time** — how long the DDL statement itself runs (index builds, constraint scans). Minimize with `CONCURRENTLY` and `NOT VALID`.
2. **Waiting time** — how long the migration waits for existing transactions to finish before it can acquire the lock. Minimize by running migrations during low-traffic periods or by setting `lock_timeout`.
3. **Connection pool pressure** — queries queuing behind a lock consume connections. The longer the wait, the more connections pile up. Minimize by keeping operations small.
4. **Operations per transaction** — more operations in one transaction means longer lock hold time and higher deadlock risk. Keep migration files small and focused.

---

## Safe vs Unsafe: Quick Lookup

| PostgreSQL statement | Lock | Safe during traffic? | Notes |
|---|---|---|---|
| `ALTER TABLE ADD COLUMN` (constant/no default) | `ACCESS EXCLUSIVE` (metadata only, fast) | ✅ | Lock held milliseconds |
| `ALTER TABLE DROP COLUMN` | `ACCESS EXCLUSIVE` (metadata only, fast) | ✅ | Lock held milliseconds |
| `ALTER TABLE SET NOT NULL` (no valid CHECK) | `ACCESS EXCLUSIVE` (full table scan) | ❌ | Can take minutes |
| `ALTER TABLE SET NOT NULL` (with valid CHECK) | `ACCESS EXCLUSIVE` (metadata only, fast) | ✅ | PostgreSQL 12+ skips scan |
| `ALTER TABLE ALTER COLUMN TYPE` (no rewrite) | `ACCESS EXCLUSIVE` (metadata only, fast) | ✅ | Only safe casts: varchar widening, varchar→text, numeric precision increase |
| `ALTER TABLE ALTER COLUMN TYPE` (rewrite) | `ACCESS EXCLUSIVE` (full table rewrite) | ❌ | Can take minutes |
| `ALTER TABLE ADD CONSTRAINT FK` | `SHARE ROW EXCLUSIVE` (full scan, child + referenced table) | ❌ | Blocks writes (not reads) on both tables for scan duration |
| `ALTER TABLE ADD CONSTRAINT FK NOT VALID` | `SHARE ROW EXCLUSIVE` on both tables (no row scan — lock held milliseconds) | ✅ | No row scan; lock held milliseconds |
| `ALTER TABLE DROP CONSTRAINT` (FK) | `ACCESS EXCLUSIVE` on child table + referenced table | ❌ | Blocks reads + writes on both tables |
| `ALTER TABLE VALIDATE CONSTRAINT` (FK) | `SHARE UPDATE EXCLUSIVE` (child) + `ROW SHARE` (referenced table) | ✅ | Both non-blocking; long-running scan on child table |
| `ALTER TABLE ADD CONSTRAINT CHECK` | `ACCESS EXCLUSIVE` (full table scan) | ❌ | |
| `ALTER TABLE ADD CONSTRAINT CHECK NOT VALID` | `ACCESS EXCLUSIVE` (metadata only, fast) | ✅ | |
| `ALTER TABLE RENAME COLUMN` | `ACCESS EXCLUSIVE` (metadata only, fast) | ❌ | Fast but breaks old code |
| `ALTER TABLE RENAME TABLE` | `ACCESS EXCLUSIVE` (metadata only, fast) | ❌ | Fast but breaks old code |
| `CREATE INDEX` | `SHARE` | ❌ | Blocks writes for full build |
| `CREATE INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | ✅ | Non-blocking |
| `DROP INDEX` | `ACCESS EXCLUSIVE` | ❌ | Blocks reads + writes |
| `DROP INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | ✅ | Non-blocking |
| `CREATE TABLE` / `DROP TABLE` | `ACCESS EXCLUSIVE` | ✅ | No live code references table |
