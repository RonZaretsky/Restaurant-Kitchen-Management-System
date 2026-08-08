# Deferred Work

## Deferred from: code review of story-1-0 (2026-08-08)

- **`get_session` missing `await` on `container.database()`** — `backend/clients/database.py:9`
  raises `AttributeError` on the first real DB-backed request, since the async resource
  provider returns a Future, not the `Database` instance. Pre-existing bug on a file Story 1.0
  was not allowed to touch. Fix is a single `await`. Story 1.1 should fix this when it wires the
  first real route through `SessionDep`.
- **`db_session` fixture has no per-test transaction isolation** — `backend/tests/conftest.py:88-97`
  opens a plain session against the session-scoped `migrated_database` with no rollback or
  truncation between tests. Unreachable today because only read-only tests exist; the first
  story that adds a write-test needs to wrap this in a savepoint/rollback or truncate strategy,
  or state changes will leak across tests in the same run.
- **`migrated_database` fixture has no per-worker uniqueness** — `backend/tests/conftest.py:72-84`
  hardcodes one database name. Fine today since there is no `pytest-xdist` dependency and no CI
  pipeline. Revisit if parallel test execution or CI is introduced, since concurrent runs would
  race on the same `DROP DATABASE` / `CREATE DATABASE` calls.
- **DSN-building duplicated three times** — the `postgresql+asyncpg://...` f-string appears in
  `backend/container.py`, `backend/alembic/env.py:51-54`, and `backend/tests/conftest.py:32-34`.
  A shared helper is the honest fix, but `container.py`'s function signature was on Story 1.0's
  must-not-change list, so consolidating now would mean touching that file anyway or adding a
  new shared module for a one-line string. Revisit if a fourth consumer appears.
- **No clear-error guard when Postgres is unreachable** — `backend/tests/conftest.py`'s DB
  fixtures raise a raw `ConnectionRefusedError` deep in setup if Postgres isn't running, rather
  than one message pointing at "start Postgres first" (`docker compose up`). DX polish only, not
  a correctness bug.
