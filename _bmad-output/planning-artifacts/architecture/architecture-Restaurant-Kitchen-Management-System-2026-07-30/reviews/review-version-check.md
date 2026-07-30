# Version Check — ARCHITECTURE-SPINE.md Stack Table

**Reviewed:** 2026-07-30 (web searches run "as of late July 2026")
**Scope:** every version named in the Stack table + inline in ADs (AD-4 Alembic async template, AD-13 React Router/MUI/TanStack Query). Report only — spine not modified.

**Verdict:** No hard incompatibilities found among Backend or Frontend packages. Two real drift findings worth Ofek's attention: **pnpm 9.15.0 is past End-of-Life**, and **TypeScript ~5.7.2 / Vite ^6.0.5 are each ~2 majors behind current** (functional, not broken). Everything else checks out as either exactly current or a safely-satisfied floor (`>=`).

---

## Backend

| Item | Spine says | Verified state (Jul 2026) | Verdict |
| --- | --- | --- | --- |
| Python | ≥3.12 | Latest 3.12.x patch is 3.12.13 (Mar 2026); Python 3.14 is the current feature line, 3.12 still in active security support. | OK — floor satisfied, not EOL. |
| FastAPI | ≥0.115.0 | Latest is 0.141.1 (Jul 29, 2026). | OK — floor easily satisfied, package current and active. |
| dependency-injector | ≥4.41.0 | 4.41.0 real (Dec 19, 2022). Latest is 4.49.1 (Jun 18, 2026). | OK — floor satisfied. |
| SQLAlchemy (asyncio) | ≥2.0.0 | Latest 2.0.x is 2.0.51 (Jun 15, 2026); 2.1 is in beta (2.1.0b3, Jun 27, 2026), not GA. `[asyncio]` extra is correctly required — greenlet no longer installs by default. | OK — floor satisfied, extra syntax correct. |
| asyncpg | ≥0.29.0 | Latest is 0.31.0 (Nov 24, 2025). | OK — floor satisfied, package active. |
| Alembic | 1.18.5 (async template) | **Exact match** — 1.18.5 is literally the current latest release (Jun 25, 2026). `alembic init -t async` is the officially documented bootstrap for an async DBAPI (asyncpg) driven by a SQLAlchemy `AsyncEngine`; alembic itself runs migrations via `run_sync`, no direct async API needed. | OK — confirmed current, confirmed compatible with SQLAlchemy 2.0 async + asyncpg. |
| PostgreSQL | 16-alpine | Postgres 16 still fully supported (5-year window, EOL ~Nov 2028). Current major is 18 (18.4, May 2026); 17 also GA. Docker tag `16-alpine` / `16.14-alpine` is valid and maintained. | OK, not broken — but **2 majors behind current** (16 vs. 18). Not a compatibility problem, just worth a conscious call given this is a fresh spine, not a legacy pin. |
| loguru | ≥0.7.0 | Latest is 0.7.3 (Apr 2026). loguru has stayed on the 0.7.x line since 2023 (no 1.0 yet) — this is normal for the package, not drift. | OK. |
| openai (Python SDK) | 2.48.0 | **Exact match** — 2.48.0 released Jul 23, 2026, one week before the spine's date. Requires Python ≥3.10 (satisfied by the ≥3.12 floor). | OK — as current as a pin can be. |

## Frontend

| Item | Spine says | Verified state (Jul 2026) | Verdict |
| --- | --- | --- | --- |
| React | 19.0.0 | 19.0.0 real (initial React 19 release, Dec 2024). Latest is 19.2.8 (Jul 21, 2026); 19.1.x and 19.2.x lines both shipped since with fixes. No React 20 yet. | OK, not broken — but pinned to the *initial* 19.0.0 rather than `^19.0.0`/`~19.2`, so it misses ~7 months of patch/minor fixes. Minor note, not an error. |
| TypeScript | ~5.7.2 (strict) | 5.7.2 real (Nov 2024). **TypeScript is now on 7.0.2** (Jul 28, 2026) — Microsoft's native Go-based compiler port, versioned to jump straight from 5.x/6.x to 7.0. | **Drift — most outdated pin in the stack.** ~5.7.2 still installs and works (it's a dev-time compiler, no runtime coupling to React/Vite/Router), but it is roughly 2 majors old. Not urgent to fix for an academic/local-demo project, but flag for awareness. |
| Vite | ^6.0.5 | 6.0.5 real (Dec 2024). Vite is now on **8.1.5** (Vite 7.0 shipped mid-2025, Vite 8.0 in Mar 2026). | **Drift — 2 majors behind current.** Vite 6 is still functional and is within React Router v7's supported range (React Router v7 does not require Vite 7+; that floor is new in React Router v8). Not an incompatibility, just aged. |
| React Router | 7.8.0 (SPA/data mode) | **Exact match** — 7.8.0 is a real published version (minor release adding `loaderData` consistency + a fetcher-revalidation fix). Confirmed: in the v7 line the package is `react-router` (not `react-router-dom` — that's now a compat shim, removed entirely in v8), and "data mode" (`createBrowserRouter`) is an officially documented, first-class mode alongside declarative and framework modes — matches the spine's "SPA/data mode, not framework/SSR" framing exactly. Note: **React Router v8 is now GA** (as of ~mid-2026), so 7.8.0 is one major behind current; v8 raises the baseline to Node 22.22+, React 19.2.7+, and Vite 7+, and drops `react-router-dom` entirely — none of that forces a change for this spine's 7.8.0 pin. | OK — confirmed compatible with React 19 and Vite 6; deliberately one major behind current, which is consistent with the spine's explicit SPA/data-mode (not framework) scope choice. |
| MUI (Material UI) | "current major, React 19-compatible" | Current major is **v9** (9.2.0, Jul 2026) per npm; React 19 support was added starting at v5/v6 and carried forward through v7/v9. (Sources show v6→v7→v9 in the public npm dist-tags; a v8 dist-tag was not surfaced by search — worth a direct `npm view @mui/material versions` check at implementation time to pin the exact major, since the spine intentionally left this unpinned.) | OK — the spine's claim holds: whichever major is "current" at implementation time is React-19-compatible, that has been true since v5. |
| TanStack Query | v5 | Latest is 5.101.2 (mid-Jul 2026); v5 is still the current major for the React adapter (no v6 core release — "v6" search noise referred to the Svelte adapter). Requires React ≥18; no documented React 19 incompatibility, and React 19 usage is widely reported as working. | OK — v5 is current, no incompatibility with React 19. |
| pnpm | 9.15.0 | 9.15.0 is a real historical version, but **pnpm 9 reached End-of-Life on April 30, 2026** (no further security patches). Current stable is pnpm 11.x (11.12.0 per one source; pnpm 10 shipped Jan 2025, pnpm 11 shipped Apr 28, 2026; a 12.0.0-beta exists). | **Real finding — EOL pin.** This is the one item in the stack that isn't just "aged" but actually unsupported upstream. Recommend bumping to at least pnpm 10.x (supported through Apr 2027) before implementation locks it in. |

## Incompatibility checks requested

- **Alembic 1.18.5 + SQLAlchemy 2.0 async engine + asyncpg:** No incompatibility. This is the documented, supported combination (`alembic init -t async`, `AsyncEngine` + `run_sync`, asyncpg as the async DBAPI).
- **MUI + React 19:** No incompatibility. React 19 support has been present since MUI v5/v6 and continues in the current major (v9).
- **React Router 7 + React 19 + Vite 6:** No incompatibility. React Router v7's floor is React 18+ and it does not mandate Vite 7+ (that requirement is new in v8), so the spine's React 19 + Vite 6 pairing is fine under 7.8.0.
- **TanStack Query v5 + React 19:** No documented incompatibility found; v5's React peer range (≥18) covers 19, and this is a common pairing in practice.

## Bottom line for the spine authors

Nothing here blocks implementation and nothing requires the spine to be rewritten (per instructions, it wasn't touched). Two items are worth a conscious decision before build starts:
1. **pnpm 9.15.0 is EOL** — the only genuinely unsupported pin in the table.
2. **TypeScript ~5.7.2 and Vite ^6.0.5 are ~2 majors behind current** — functional and mutually compatible with the rest of the frontend stack as pinned, just aged.

## Sources

- [Python Release Python 3.12.13](https://www.python.org/downloads/release/python-31213/)
- [FastAPI · PyPI](https://pypi.org/project/fastapi/)
- [Dependency Injector 4.49.1 docs / changelog](https://python-dependency-injector.ets-labs.org/)
- [dependency-injector 4.41.0 · PyPI](https://pypi.org/project/dependency-injector/4.41.0/)
- [dependency-injector · PyPI](https://pypi.org/project/dependency-injector/)
- [SQLAlchemy asyncio docs (2.0)](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLAlchemy 2.1.0b1 Released](https://www.sqlalchemy.org/blog/2026/01/21/sqlalchemy-2.1.0b1-released/)
- [SQLAlchemy 2.1.0b2 Released](https://www.sqlalchemy.org/blog/2026/04/16/sqlalchemy-2.1.0b2-released/)
- [asyncpg · PyPI](https://pypi.org/project/asyncpg/)
- [Alembic 1.18.5 documentation / Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html)
- [Alembic · PyPI](https://pypi.org/project/alembic/)
- [Async migration with asyncpg · alembic Discussion #1208](https://github.com/sqlalchemy/alembic/discussions/1208)
- [postgres:16-alpine — Docker Hub](https://hub.docker.com/_/postgres)
- [PostgreSQL | endoflife.date](https://endoflife.date/postgresql)
- [PostgreSQL EOL Dates — HeroDevs](https://www.herodevs.com/blog-posts/postgresql-eol-dates-every-versions-release-end-of-life-timeline)
- [loguru | Snyk](https://security.snyk.io/package/pip/loguru)
- [loguru documentation](https://loguru.readthedocs.io/)
- [openai 2.48.0 — newreleases.io](https://newreleases.io/project/pypi/openai/release/2.48.0)
- [openai · PyPI](https://pypi.org/project/openai/)
- [react - npm (versions)](https://www.npmjs.com/package/react?activeTab=versions)
- [React 19.2.8 Release — GitHub](https://github.com/react/react/releases/tag/v19.2.8)
- [React | endoflife.date](https://endoflife.date/react)
- [TypeScript 7.0 RC — Visual Studio Magazine](https://visualstudiomagazine.com/articles/2026/06/22/typescript-7-0-rc-moves-microsofts-go-rewrite-into-the-mainline-compiler.aspx)
- [Announcing TypeScript 7.0 — TypeScript blog](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/)
- [vite - npm](https://www.npmjs.com/package/vite)
- [Vite 7.0 announcement](https://vite.dev/blog/announcing-vite7)
- [Vite Releases](https://vite.dev/releases)
- [react-router@7.8.0 CHANGELOG — GitHub](https://github.com/remix-run/react-router/blob/react-router@7.8.0/packages/react-router/CHANGELOG.md)
- [Picking a Mode | React Router docs](https://reactrouter.com/start/modes)
- [Choosing the right React Router v7 mode — LogRocket](https://blog.logrocket.com/react-router-v7-modes/)
- [React Router v8 — Remix blog](https://remix.run/blog/react-router-v8)
- [React Router v8 GA — Stackmaven](https://stackmaven.io/news/react-router-8-ga)
- [Updating from v7 | React Router docs](https://reactrouter.com/upgrading/v7)
- [How we migrated MUI X to React 19 — MUI blog](https://mui.com/blog/react-19-update/)
- [@mui/material · npm](https://www.npmjs.com/package/@mui/material)
- [Material UI Updates — Releasebot, July 2026](https://releasebot.io/updates/mui/material-ui)
- [@tanstack/react-query · npm (versions)](https://www.npmjs.com/package/@tanstack/react-query?activeTab=versions)
- [Announcing TanStack Query v5 — TanStack blog](https://tanstack.com/blog/announcing-tanstack-query-v5)
- [TanStack Query v5 React docs](https://tanstack.com/query/v5/docs/framework/react)
- [pnpm | endoflife.date](https://endoflife.date/pnpm)
- [pnpm 11.0 — pnpm blog](https://pnpm.io/blog/releases/11.0)
- [pnpm 10.26 — pnpm blog](https://pnpm.io/blog/releases/10.26)
- [pnpm EOL — eosl.date](https://eosl.date/eol/product/pnpm/)
