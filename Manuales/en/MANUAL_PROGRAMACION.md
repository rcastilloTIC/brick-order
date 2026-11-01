# VALBRICK | Public | Programming and maintenance handbook

**V93-RC1**  |  **2026-11-01**  |  **AGPL-3.0-only**  |  **VALBRICK**

> Based on the inspected source files of the validated edition. Release candidate; not a production certification.

---

## Purpose and maintenance contract
This handbook is written for someone still learning Python **and** for an engineer taking complete technical responsibility. It is not a generic Flask introduction: it documents **this repository**, its financial invariants and code-derived appendices listing routes, models, services and tests. You must still read the source before changing business rules.

- **Edition and revision**: Public **V93-RC1**. Keep a dedicated repository and deployment for this edition.
- **Reported validation baseline**: 532 tests passed, 1 skipped, 167 subtests, no Docker failures; E2E and release gates passed.
- **Not production-certified V1.0**: server hardening, HTTPS, manual acceptance and dependency policies remain the deployment owner's responsibility.
- **Non-negotiable business invariant**: never turn rejected votes into purchases, double-count a commitment, mix campaign years, drop selected quantities or erase historic records.

### How to study this codebase
First pass: chapters 1-6, then look at `app/models.py` and trace a form through `app/main/routes.py`. Second pass: chapters 7-16 and run a pure function test without a database. Third pass: annual lifecycle, SQL and E2E tests. Before changing code, write a regression test that would fail if the previous behaviour were broken.

## 1. Technical glossary for beginners
**Function**: a `def name(...):` block with inputs and outputs. **Module**: a `.py` file. **Import**: bringing another function/class into scope. **Class**: blueprint for objects. **ORM model**: Python class mapped to an SQL table. **Database**: SQLite file containing rows, indexes and triggers. **HTTP route**: URL mapped to Flask code. **GET**: typically reads data; **POST**: generally changes data. **Blueprint**: group of Flask routes. **Jinja template**: HTML with `{{ ... }}` expressions and `{% ... %}` control structures. **Transaction**: writes that are committed or rolled back together. **Commit**: persist; **rollback**: abandon pending changes. **Fixture**: controlled test data and environment. **E2E**: test crossing the real application layers.

A request generally follows this path:

```text
Browser -> HTTPS/Caddy -> Gunicorn -> Flask route (/vote)
   -> login + CSRF + campaign checks
   -> quantity_rules / commitment_ledger
   -> SQLAlchemy session -> SQLite
   -> commit -> redirect + flash -> HTML template
```

A redirect is not proof of successful insertion. A route may return 302 while displaying a business error. Assert the **database, amounts and messages**, not just status codes.

## 2. Repository map and runtime entry
| Path | Responsibility |
|---|---|
| `run.py` | Loads `.env`, selects configuration, creates app, calls `init_db()` and exposes `app` for Gunicorn. |
| `wsgi.py` | Alternate Flask entry; not an automatic replacement for container `run.py`. |
| `config.py`, `.env.example` | Security, database, cost and limit settings. |
| `app/__init__.py` | `create_app` factory, extensions, auth, CSRF, rate limiting, proxy and SQLite schema preparation. |
| `app/models.py` | Tables, ORM relationships and protection against deleting parents with orders. |
| `app/auth/routes.py` | Login, profile, password change, signed document and onboarding. |
| `app/main/routes.py` | User/admin dashboards, voting, phases, imports, final exports and history. |
| `app/main/translation_admin.py`, `app/i18n.py` | ES/EN translations and administrator translation editor. |
| `app/services/` | Reusable domain logic: campaigns, limits, order materialisation, exports, archive and backups. |
| `orders/`, `products/` | Auxiliary Flask blueprints. |
| `templates/`, `static/` | Jinja HTML, CSS and JavaScript. |
| `scripts/` | Maintenance, audit, import, backups and isolated test runners. |
| `tests/` | Unit contracts, SQLite integration, HTTP, security, E2E and release tests. |
| `docs/` | Original deployment and recovery notes. |
| `data/` | Persistent deployment volume; NEVER commit it publicly. |
| `LICENSE`, `NOTICE`, `EDITION`, `VALBRICK_EDITION` | Licensing and edition boundary. |

**First source-reading exercise:** locate the `/vote` form in `templates/user_dashboard.html`, find `vote` in `app/main/routes.py`, follow its service calls and affected models. Repeat for `/admin/order/generate`.

## 3. Reproducible setup and first commands
Production runs **Python 3.11**, Flask 2.2-2.x, Flask-SQLAlchemy 3.x, SQLite, Gunicorn, openpyxl and fpdf2, plus packages in `requirements.txt`. Use Git and Docker Compose. Never run isolated test scripts against production volumes.

**A. Recommended disposable Docker checks in a separate checkout:**

```sh
sh scripts/run_v93_release_isolated.sh
sh scripts/run_v92_e2e_isolated.sh
sh scripts/run_full_tests_isolated.sh
```

Test runners build Docker images without mounting your real data or exposing ports. Host pytest is not required. Save their baseline output before editing code.

**B. Optional local development with fictional data only:**

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
# Edit .env with unique SECRET_KEY, ADMIN_PASSWORD,
# SITE_ACCESS_PASSWORD, DEFAULT_USER_PASSWORD and valid SOURCE_CODE_URL.
# Set FLASK_ENV=development, HOST=127.0.0.1, PORT=5001.
python run.py
```

`run.py` imports config classes with fail-fast checks: set required secrets even in development. The default `DATABASE_URL` points to local `mi_app.db`; **explicitly use a throwaway database**, never a real user's copy. Rerun Python 3.11 tests after edits.

**C. Observe deployment without changing data:**

```sh
docker compose config --quiet
docker compose ps
docker compose logs --tail=80 app
```

## 4. Flask and request lifecycle
`create_app()` in `app/__init__.py` creates Flask, applies configuration **before** deciding whether `X-Forwarded-*` headers can be trusted, initialises SQLAlchemy, Flask-Login, CSRFProtect, Flask-Limiter and i18n, then registers `auth`, `main`, `translations_admin`, `products` and `orders` blueprints. `before_request` enforces the site passphrase (when configured), mandatory password change and, for participants, enrolment/signed document/approval in the active campaign.

Flask sessions use HttpOnly, SameSite Lax and `Secure=true` in production. POST forms have CSRF protection: copying a route but omitting its token is not an acceptable workaround. `TRUSTED_PROXY_COUNT` enables ProxyFix only behind a proxy that sanitises forwarded headers. Login attempt throttling is separate from financial vote limits.

**Secure route pattern:** authenticate -> identify active campaign -> verify annual permissions -> read and validate all input -> enforce phase and limits -> write in one transaction -> audit and commit -> display result. Do not commit from a helper participating in a larger transaction.

## 5. Configuration: where each setting belongs
| Key | Meaning / caution |
|---|---|
| `SECRET_KEY` | Flask session signing key, unique and never committed. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Initial administrator identity. `init_db()` requires at least 12 characters. |
| `DEFAULT_USER_PASSWORD` | Fallback for user imports; never publish it. |
| `SITE_ACCESS_PASSWORD` | Separate site-entry passphrase, not a user password. |
| `DATABASE_URL` | SQLite location; Docker uses `sqlite:////data/db/app.sqlite`. |
| `DECLARATION_UPLOAD_FOLDER` | Signed PDFs, private persistent directory. |
| `ORDER_EXPORT_FOLDER` | Excel and PDF bundles, private persistent directory. |
| `BACKUP_FOLDER` | Backups, never put on GitHub. |
| `SOURCE_CODE_URL` | HTTPS URL for this edition's corresponding AGPL source. |
| `TRUSTED_PROXY_COUNT` | Count of trusted proxies overwriting `X-Forwarded-*`; 0 without proxy. |
| `SESSION_COOKIE_SECURE` | HTTPS-only session cookies, should be true in production. |
| `PORT` | Container/host port, normally 5001. |
| `PHASE_ONE_ORDER_LIMIT` | Personal budget default EUR 235; can be overridden annually and by test mode. |
| `MIN_TOTAL_ORDER_AMOUNT` | Collective minimum default EUR 4,800; annual override possible. |
| `MAX_REFERENCES_PER_USER` | First-phase reference cap default 10. |
| `PHASE_TWO_REFERENCE_LIMIT` | Second-phase cap default 20. |
| `FINAL_SELECTION_LIMIT` | Final selected references default 85. |
| `DEFAULT_LANGUAGE`, `SUPPORTED_LANGUAGES` | Default and allowed languages, usually `es,en`. |
| `ENABLE_ANNUAL_ACTIVATION` | Explicit gate: only `1` allows prepared draft activation after preflight. Do not enable without route review. |

**Annual configuration** must not be stored as bare global settings. `app/services/campaign_settings.py` uses an `ANNUAL_KEYS` allowlist and names `annual_<campaign_id>_<key>`. A new annual setting requires adding it to the list **and writing cross-year isolation tests**. The Extended RC1/RC2 incident was precisely a missing private key in that list, producing HTTP errors.

## 6. Git, branches, changes and releases
Each edition has its own repository; never copy `app/main/routes.py` from one to the other because private and public procedures are incompatible. An ordinary change uses:

```sh
git checkout -b fix/order-summary
# edit one module and add/extend a regression test
sh scripts/run_v93_release_isolated.sh
sh scripts/run_v92_e2e_isolated.sh
sh scripts/run_full_tests_isolated.sh
git status --short
git diff --check
git add app tests docs
git commit -m "Test and fix selected order summary"
```

Review diffs before committing. Keep `LICENSE`, `NOTICE` and VALBRICK attribution. Exclude `.env`, `data/`, backups, SQLite, certificates, password CSVs, real PDFs and `.pytest_cache` via `.gitignore`; inspect Git history as well as the latest commit.

## 7. Domain model: identity, campaign and data ownership
The correct model is **not** "a user has one global order". There are two dimensions: a durable `User` may exist across years; `CampaignParticipation` records enrolment/approval for **one** `Campaign`. Rows in `Product`, `UserVote`, `UserFavorite` and `Order` carry `campaign_id` and must be queried within the active year. Campaign states include `legacy_active`, `draft`, `archived` and `closed`. A `draft` is preparation, not permission to vote.

```text
User (durable identity) ----< CampaignParticipation >---- Campaign (year)
   |                                  |                          |
   +---- UserVote --------------------+---- Product --------------+
   +---- Order ---------------------------- Product [selected]     |
   +---- UserFavorite --------------------- Product                |
   +---- ActionLog (audit)                                         |

Config: namespaced annual settings / campaign-specific phase
CampaignInsightSnapshot: yearly aggregate observations
```

SQLite has constraints and partial indexes, annual-membership triggers, cross-year product guards, reverse membership protections and archived-row protections. **These are critical**, protecting the database even from SQL written outside Flask. `app/__init__.py:init_db` and `_ensure_schema` validate and backfill known columns; `db.create_all()` is not a general migration system capable of fixing every legacy dataset.

**Query invariant:** prefer `products_query()`, `orders_query()`, `votes_query()` and `favorites_query()` in `app/services/campaign_data.py` over unscoped operational table queries. A `User.query` can be global because identities persist; purchasing permissions nevertheless require joining the **current year's** participation.

## 8. States, calendar and atomic transitions
The phase is stored per year as `phase_campaign_<id>` (module `campaign_phase.py`). A global `phase` fallback exists only for a database with exactly one campaign. Never inherit an archived year's `order` phase when activating a new year. Core states:

```text
first --activate-second--> second --advance-final--> final
    --advance-order + selection + materialisation (one transaction)--> order
```

`annual_readiness.inspect_annual_readiness()` checks campaign registry, null years, unenrolled users, cross-year relations and draft preparation. `campaign_calendar` checks dates and overlap. `campaign_activation.activate_prepared_draft()` requires `ENABLE_ANNUAL_ACTIVATION=1`, confirmation `ACTIVAR <year>`, a valid calendar and clean preflight. Old databases may need specific migrations before enabling this gate.

**Atomicity of `final -> order`:** `compute_final_selection(persist=False)` checks ties/limits without writing. Then selection is persisted, `materialize_selected_commitments()` adds missing quantities, `assert_selected_commitments_materialized()` verifies vote floors, and `set_current_phase('order', commit=False)` changes phase. **One `db.session.commit()`** closes the whole operation. Any exception triggers a complete rollback.

## 9. Commitments, cents and quantities
A major legacy hazard is two representations of one purchase: `UserVote` and `Order`. `commitment_ledger.committed_total()` aggregates each source by product and takes **the greater total quantity per product** between votes and orders. Example: reference A with 50 voted and 50 ordered units counts 50, not 100; reference B with 25 votes and 0 orders still counts 25. `max(total_voted, total_ordered)` across the entire order would also be wrong because it loses disjoint products.

After final selection, `effective_commitment()` includes only selected products. Rejected-product votes remain for history, but are not materialised or charged. `validate_quantity()` uses `Decimal`: prices `<= 1.35` require minimum 25 and step 25; higher prices require minimum 10 and step 10. It rejects booleans, NaN/infinity, negative prices and non-integer quantities. For monetary aggregation use `Decimal(str(price))`, never naive cumulative floats.

`missing_order_floors()` plans `(user, product) -> max(0, voted - ordered)`, selected products only. `materialize_selected_commitments()` writes the deficit and is **idempotent**: rerunning it must not duplicate quantity. `assert_selected_commitments_materialized()` gates exports. **Never delete rejected votes solely because a product was excluded:** they are historical evidence.

### Reasoning exercise (no execution)
Suppose a participant voted A=25, B=10 and has actual order A=25, B=0. Before final selection the commitment includes A and B. If only A is selected, `Order` must contain at least A=25, not B. An additive +25 for A makes A=50, not 75. Such dual-ledger cases deserve unit tests with varying prices and sources.

## 10. Ranking and final selection
`app/services/final_selection.py` aggregates votes by product, ranks candidates, handles locks/manual promotions and separates selected, excluded, tied and over-limit products. `compute_final_selection(limit=..., persist=False)` is a read-only preflight; `persist=True` can update `Product.final_selected`, `final_disabled` and `final_promoted`. Tie tests must show that SQL row ordering cannot arbitrarily decide tied items.

A final selection is not merely "has votes". `Product.final_selected` and `final_disabled` are contractual states; exports filter selected and not disabled products. Check year-specific count limits and manually locked items before releasing orders.

## 11. HTTP voting and actual limits
An authenticated participant opens `main.user_dashboard` (`/dashboard`) and sends `/vote` with `product_id` and `quantity`. The route enforces phase, active-year product, annual membership/document, quantity steps, personal budget and non-decreasing obligations. `/favorite` does not change votes; `/vote/delete` is constrained by phase and commitment protection. `orders/create` is not an unrestricted shopping cart: it is administrative and requires an approved participant.

**Change discipline:** never copy/paste financial rules into a new route. Reuse `quantity_rules`, `commitment_ledger` and campaign/selection gates. Add tests for the exact price threshold, missing product, wrong-year product, unapproved user and simultaneous requests.

## 12. From orders to Excel, PDF and archive
`order_exports.build_final_order_context()` reads votes before ordering, and **Order** during `order` and `final_extension`. It returns product totals and participant breakdowns. `assert_current_export_summary()` recomputes a fingerprint to block stale or forged summaries. `generate_order_files()` checks materialised vote floors and generates:

| Output | Contents |
|---|---|
| `pedido_total_<timestamp>.xlsx` | One `Pedido` sheet: reference, name, colour, price, quantity, amount and total. |
| `pedido_por_pieza_<timestamp>.zip` | Combined PDF and individual PDFs by reference. |
| `pedido_por_usuario_<timestamp>.zip` | Combined PDF and per-user PDFs; includes configured payment/cost details. |

Per-year names are stored in `final_order_excel`, `final_order_piece_pdf`, `final_order_user_pdf`; `final_order_generated_at` marks closure. The fallback PNG must be valid for fpdf2 (an invalid one was found during V92). Downloads check allowed paths and basenames with `export_path_safety.safe_export_path`.

Annual archiving (`campaign_archive.archive_completed_campaign`) verifies the active year and phase, export timestamp, internal XLSX ZIP integrity, header, and **exact** data/totals against current orders. It rejects extra sheets, formulas where numeric cells are required, duplicate references, changed quantities and symlinks outside the export directory. Archiving sets `archived` with an audit log and **retains historical orders**. A hand-edited Excel is not authoritative.

## 13. Payment details and internal tasks
IBAN and due date are annual settings. Updating payment details can launch regeneration **in a daemon thread**: a "started" flash does not guarantee files have been written or that the thread survives a process restart. Future evolution should use a persistent work queue or explicit task with status, logs and idempotent retries if operational reliability warrants it.

Tax and shipping are calculated from configured costs, not arbitrarily edited spreadsheet cells. A refactor must preserve allocation rules and reconcile PDFs, workbook and orders.

## 14. Imports: CSV, Excel and drafts
`_handle_users_csv_upload()` requires `username,password` in UTF-8 and rejects `is_admin` or privileged account modification. Existing identities retain passwords and previous approvals; annual enrolment is created separately. `_parse_products_excel()` recognises `Material`, `Communication number` or `reference`, `Description` or `name`, plus price/image/category fields. Never assume arbitrary supplier workbooks fit: build a known-header fixture and test duplicates, missing values, non-finite prices and references with commitments.

`draft_catalog_import.validate_draft_catalog_rows()` and `import_draft_catalog()` prepare a catalogue under a `draft` campaign transactionally. A draft may contain a catalogue and annual participants, but **must not contain orders, votes or favourites** before activation. A new year is never created by deleting the preceding year's data.

## 15. Backups, file safety and recovery
**Web backup:** `backups.create_phase_backup()` creates phase ZIP files and can be called by administrative transitions. Last backup and error logs have admin-only downloads. **Web restoration:** `/admin/backup/restore` deliberately returns 409: replacing SQLite and documents during live Flask sessions is unsafe.

**Offline backup:** `scripts/create_offline_backup.sh` stops the app and uses `create_offline_backup.py`, keeping ZIP files in `data/backups`. **Offline restore:** `scripts/restore_offline.sh` stops the app, runs `restore_offline.py` inside a networkless Python container, validates ZIP/manifest/edition/SQLite/phases/paths, swaps prepared directories and retains `data.pre-restore-*`. Regression tests simulate mid-swap failure and demand rollback. Any external scheduler must be stopped separately.

A readable ZIP is not necessarily trustworthy. Reject dangerous duplicate members, `../` (zip slip), absolute paths, unexpected files, symlinks and malformed payloads. Never use `ZipFile.extractall` on untrusted input without validation. Never post real backups or signed PDFs to public issues.

## 16. Application security and key threats
| Threat | Protection to preserve |
|---|---|
| Access to someone else's orders | `login_required`, `_ensure_admin`, `require_campaign_participant`, `campaign_id`. |
| Cross-site form submissions | CSRFProtect and hidden form tokens in Jinja. |
| Brute-force login | Flask-Limiter on login/site-access routes. |
| Cross-year user permissions | `CampaignParticipation` with this year's document/status, not historic `User` flags. |
| Global phase/settings confusion | `get_campaign_phase()`, `ANNUAL_KEYS`, annual preflight. |
| Financial miscount | `Decimal`, `effective_commitment()`, materialisation and export fingerprint. |
| File path injection | `safe_export_path`, validated basenames and symlink rejection. |
| Misconfigured proxy | `TRUSTED_PROXY_COUNT=0` unless behind an appropriate HTTPS proxy. |
| Exposed secrets | Private `.env`, `.gitignore`, unique secrets and sanitised logs. |
| Live restore corruption | Offline restore with stopped app, integrity checks and rollback. |

External images require network access and can fail; PDF generation uses a local fallback. Track dependency advisories and eventually lock the validated resolved versions. SQLite concurrency and external writers must respect `BEGIN IMMEDIATE`, busy timeouts and locking; do not claim PostgreSQL support because `libpq-dev` happens to be installed in Docker.

## 17. Public-only subsystem: insufficient-order notices
**Source:** `app/services/shortage.py`; models `ShortageWindow`, `ShortageAcknowledgement`; endpoints `/admin/shortage`, `/shortage/acknowledge`, `/shortage/increase`. Extended has neither this service nor these tables.

1. `order_total(campaign_id)` calculates money from **Order**, not the raw vote total. `minimum_total()` reads the annual minimum or configuration default.
2. `open_window(actor_id, days)` requires active campaign in `order`, total below minimum and no prior decision. The window is 1-30 integer days. It inserts an open `ShortageWindow` and an audit record.
3. `acknowledge(user_id)` requires approved membership and signed PDF for this year, plus a currently open unexpired notice. It stores `ShortageAcknowledgement`; repeating it is idempotent.
4. `add_extra_order()` enforces acknowledgement, selected product, valid price/quantity steps, remaining budget and protected commitments. It opens SQLite `BEGIN IMMEDIATE` before read-check-write to serialise concurrent requests. A PostgreSQL migration would need a redesigned locking strategy.
5. `reconcile(now)` resolves `reached` once the minimum is met (even at the deadline); otherwise, after expiry, it resolves `cancelled`. Merely importing this module does not guarantee a scheduled worker.
6. `cancel(actor_id)` supports a controlled administrator cancellation during `order`, with audit log and no historical deletion.

**State machine:** `open -> reached` or `open -> cancelled`; the decision cannot simply be reopened. Timing uses server UTC. External reconciliation scheduling, when provided, must use the same data and permission guarantees. **Relevant tests:** `test_v85_shortage.py`, `test_v86_shortage_increase.py`, `test_v92_campaign_e2e.py`, `test_iteration_46_public_only.py` and V92 concurrency contracts.

### Essential concurrency regression
Two users try to increase simultaneously; either increase fits in isolation but not both combined. Only the permitted total may commit; the other must fail/retry consistently without exceeding the ceiling. Another test must prove expiry does not change an archived campaign's rows.

## 18. Frontend, translations and accessibility
The UI uses **Jinja2 + Bootstrap 5.3 CDN + local CSS** (`static/css/`) and an appearance script (`static/js/valbrick-appearance.js`). `templates/base.html` defines navigation, ES/EN selection, light/dark appearance, source link and main layout. `templates/admin_dashboard.html` includes phase-sensitive forms. Changing a button label is not enough: the HTTP POST must enforce **the same security condition**.

Base translations live in `app/translations/es.json` and `en.json`. `app/i18n.py` selects language from the session or request, falls back to defaults and loads JSON overrides from `/data/translations`. `app/main/translation_admin.py` constrains keys, lengths and imports. To add a visible message: create the key in both JSON files, use `{{ _('key') }}` in Jinja and test language selection and fallback. Never put credentials or private URLs in translation content.

**Manual visual QA:** mobile screens, keyboard, navigation, errors, CSRF tokens, light/dark mode, PDFs without images and HTTPS links. HTML button regex tests do not replace browser acceptance.

## 19. Tests: layers and quality commands
| Layer | Examples | Contract |
|---|---|---|
| Pure functions | `test_quantity_rules.py`, `test_commitment_ledger.py` | Exact quantities and Decimal arithmetic. |
| ORM / SQLite | `test_order_materialization.py`, `test_campaign_write_guards.py` | FKs, triggers, annual isolation, rollback. |
| HTTP | `test_v93_release_http.py`; `test_v90_private_extension_http.py` where applicable | Session, authority, phase and actual results. |
| Security | `test_backup_zip_safety.py`, `test_proxy_configuration.py` | Malformed ZIP, access, proxy and paths. |
| E2E | `test_v92_campaign_e2e.py` | Fictional year, phases, Excel/PDF and archive. |
| Release | `test_v93_offline_restore.py`, `test_v93_release_security_contract.py` | Recovery, rollback, non-root runtime. |

- `run_v93_release_isolated.sh`: offline recovery plus visible button and transition HTTP tests.
- `run_v92_e2e_isolated.sh`: two real paths through the fictional campaign.
- `run_full_tests_isolated.sh`: complete pytest suite; Extended includes private invitation tests.
- `.github/workflows/checks.yml`: `push`/`pull_request` checks installing requirements, compiling and running pytest on GitHub.

**Reported baseline for these source packages:** Public V93-RC1 532 passed, 1 skipped, 167 subtests; Extended V93-RC2 517 passed, 1 skipped, 160 subtests. The single skipped cross-edition comparison cannot work in an edition-isolated container. The intentional duplicate-ZIP warning and SQLAlchemy `LegacyAPIWarning` are not test failures but remain maintenance items.

### Minimal pure unit test
This existing pure helper does not touch a database:

```python
from app.services.quantity_rules import validate_quantity

def test_quantities_step_and_threshold():
    assert validate_quantity(1.00, 25)[0] is True
    assert validate_quantity(1.00, 30)[0] is False
    assert validate_quantity(2.00, 10)[0] is True
    assert validate_quantity(2.00, 25)[0] is False
```

Run `python -m pytest -q tests/test_quantity_rules.py` **in a test environment** where pytest is installed, or use the Docker scripts. For HTTP integration reuse `tests/_v92_campaign_fixture.py`, which constructs temporary directories, users and fictional campaigns. Assert database state at the end, not only redirects.

## 20. Adding features without breaking money or history
**Guided example: show the selected total on the admin page.**
1. Define whether the number is "voted" or "ordered"; once `order` begins, effective quantity comes from `Order`.
2. Write a test for `build_final_order_context()` with two users, two references and one rejected product; verify no double count.
3. Reuse a service or write a pure amount helper. Never query every year or use unscoped global settings.
4. Add read-only context to `/admin` behind `_ensure_admin`; do not make GET mutate state.
5. Add Jinja and an i18n key in `es.json` and `en.json`; avoid duplicating financial policy in JavaScript.
6. Run pure, HTTP, E2E and full suites in disposable Docker.
7. Compare two campaigns and an unapproved user. Verify Public and Extended code never intermingle.
8. Record the change, test a backed-up deployment and publish a reviewable commit.

**Dangerous example:** adding a column to `CampaignParticipation` and calling `db.create_all()` expecting it to exist in an old database. That **does not migrate existing columns**: plan schema changes, compatibility and rollback. Use existing maintenance scripts as examples, not as permission to ALTER production tables without a backup.

## 21. SQLite migrations and atomic operations
Before altering schema: inventory tables/indexes/triggers, back up the DB, identify foreign keys and historical rows, write forward/recovery steps, and rehearse on anonymised data. Avoid `drop_all()`, mass truncation and deleting parent users/products with orders. Archived rows and historical references have special guards.

**SQLAlchemy transactions:** `db.session.add()` stages a row, `flush()` sends it without committing, `commit()` persists, `rollback()` cancels and `session.remove()` releases context. `Config.set()` commits by default and must not be called inside composite operations without understanding whether `commit=False` is supported or whether an in-session object is required. Verify real behaviour before refactoring.

**SQLite concurrency:** do not generalise from one request to two simultaneous users. Public increases and selected voting paths use writer reservation to serialise budget checks and changes. A new handler that reads the total, waits, then writes without a lock could exceed the ceiling. Test concurrent requests with real SQLite; mocks alone cannot prove serialisability.

## 22. Symptom-led troubleshooting
| Symptom | Likely cause / first investigation |
|---|---|
| `Not an annual setting` | Key missing from this edition's `ANNUAL_KEYS`; verify yearly namespace and add regression. |
| Redirect but no change | A `flash` may explain rejection; inspect phase, permissions, request data and DB. |
| PDF error / missing `final_order_generated_at` | Inspect fpdf2 logs, fallback PNG, remote image and export-folder permissions. |
| Excel contains fewer units than selected votes | Missing materialisation/sync; compare `Order` and `UserVote` per user/product. |
| Edited Excel cannot archive | Check `Pedido` sheet, exact header, cell types, duplicates and match to orders. |
| Wrong next-year phase | Check `phase_campaign_<id>` and accidental global `Config.get('phase')`. |
| `403` when voting | Check active account, this year's approved membership and signed PDF, not just `User.declaration_validated`. |
| `409` restoring on web | By design; use offline restore with server stopped. |
| `sqlite3.OperationalError: database is locked` | Check external writer, busy timeout, long transactions and `BEGIN IMMEDIATE`. |
| Cannot write `/data` | Check UID/GID 10001, bind mount permissions and disk capacity. |
| Login lost behind HTTPS | Check Secure session cookie and trusted proxy forwarding. |
| GitHub Actions fails, Docker passes | Compare env vars, resolved versions and CI command; never hide failure. |

## 23. Operations, observability and improvement roadmap
The Dockerfile creates a Python runtime, installs requirements, switches to UID/GID 10001, starts `gunicorn --workers 1` and exposes 5001 internally. Compose binds `127.0.0.1:${PORT:-5001}:5001`, mounts `./data:/data`, uses a TCP healthcheck and `restart: unless-stopped`. The HTTPS proxy is configured **outside** this container; `Caddyfile.example` points to the host loopback address.

Recommended maintenance: TLS renewal alerts, disk/backups monitoring, regular recovery rehearsals, externally scheduled `flask capture-insights` snapshots if desired, integrity/readiness reviews before each year, dependency advisory scans, a reproducible lockfile and retirement of SQLAlchemy `LegacyAPIWarning`. The web restore control does not replace the offline runbook.

**Known debt:** ranged dependencies without full lock; legacy migration comments; transitional dual `UserVote`/`Order` ledger; daemon-thread document regeneration in certain flows; SQLite without a persistent task queue; production-host accessibility and recovery acceptance still to be performed. Prioritise financial/data correctness over cosmetic UI changes.

## 24. Twelve-step beginner-to-maintainer learning track
| Level | Practical exercise | Completion criterion |
|---|---|---|
| 1 | Trace `/vote` through SQLAlchemy. | Locate route, service, model, commit, permissions and test. |
| 1 | Add one translated string to a template. | Present in ES/EN; fallback never displays raw key. |
| 1 | Write a pure `validate_quantity()` test. | Passes on Python 3.11 and rejects invalid value. |
| 2 | Map phases and administrator POSTs. | No `order` before `final`, no premature export. |
| 2 | Test the same commitment in vote and order. | No double-counted amount per product. |
| 2 | Add an excluded product to a fixture. | Not materialised/exported; vote retained. |
| 3 | Safely change a year-specific service. | Two-year test; no global config leakage. |
| 3 | Test a manipulated XLSX. | Rejected without changing `Campaign.status`. |
| 3 | Rehearse fictional backup/rollback. | Old data preserved after simulated failure. |
| 4 | Plan an annual schema field migration. | Upgrade, preflight, backup, rollback and tests specified. |
| 4 | Rehearse concurrent budget updates. | No ceiling breach or partial writes. |
| 4 | Test GitHub -> HTTPS proxy -> isolated Docker. | Green suite, secure sessions, clean logs, external backup. |

**Independent maintainer standard:** someone taking over should locate a defect, reproduce it with a test, explain the affected model/phase, make a minimal fix, validate both editions **separately**, and roll back a deployment without data loss.

## 25. Appendix: complete ORM model dictionary

This inventory was extracted from `app/models.py`, not from a live production SQLite schema. Columns, foreign keys and constraints use their actual source declarations. Review `__table_args__`, indexes and installer-managed triggers before migrations.

### `User` - `user`

Account identity, password hash, personal data and roles; an account alone is not yearly approval.

Source: `app/models.py:8`. Fields: **15**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `username` | `db.Column(db.String(50), unique=True, nullable=False)` |
| `password_hash` | `db.Column(db.String(128), nullable=False)` |
| `first_name` | `db.Column(db.String(50))` |
| `last_name` | `db.Column(db.String(50))` |
| `dni` | `db.Column(db.String(15))` |
| `age` | `db.Column(db.Integer)` |
| `agreements_accepted` | `db.Column(db.Boolean, default=False)` |
| `active` | `db.Column(db.Boolean, default=True)` |
| `is_admin` | `db.Column(db.Boolean, default=False)` |
| `declaration` | `db.Column(db.String(255))` |
| `paid` | `db.Column(db.Boolean, default=False)` |
| `must_change_password` | `db.Column(db.Boolean, default=True)` |
| `declaration_file` | `db.Column(db.String(255))` |
| `declaration_validated` | `db.Column(db.Boolean, default=False)` |

**Relationships:** `orders`, `votes`, `favorites`, `action_logs`.

### `Product` - `product`

Yearly product catalogue, price, colour, final selection and lock state.

Source: `app/models.py:37`. Fields: **17**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)` |
| `image_url` | `db.Column(db.String(255))` |
| `reference` | `db.Column(db.String(100), nullable=False)` |
| `name` | `db.Column(db.String(255))` |
| `price` | `db.Column(db.Float, nullable=True)` |
| `is_locked` | `db.Column(db.Boolean, default=False)` |
| `colour_id` | `db.Column(db.String(50))` |
| `color_bl` | `db.Column(db.String(255))` |
| `present_in_2024` | `db.Column(db.Boolean, default=False)` |
| `main_group_top` | `db.Column(db.String(100))` |
| `main_group` | `db.Column(db.String(100))` |
| `main_group_sub` | `db.Column(db.String(100))` |
| `present_in_2025` | `db.Column(db.Boolean, default=True)` |
| `final_selected` | `db.Column(db.Boolean, default=False)` |
| `final_disabled` | `db.Column(db.Boolean, default=False)` |
| `final_promoted` | `db.Column(db.Boolean, default=False)` |

**Relationships:** `orders`, `votes`, `favorites`.

### `Order` - `order`

Actual user/product/campaign quantity; source of exported orders.

Source: `app/models.py:62`. Fields: **6**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `product_id` | `db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)` |
| `quantity` | `db.Column(db.Integer, nullable=False)` |
| `timestamp` | `db.Column(db.DateTime, default=datetime.utcnow)` |

**Relationships:** `user`, `product`.

### `ActionLog` - `action_log`

Auditable participant and administrator actions.

Source: `app/models.py:75`. Fields: **5**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `action` | `db.Column(db.String(40), nullable=False)` |
| `detail` | `db.Column(db.String(255))` |
| `created_at` | `db.Column(db.DateTime, default=datetime.utcnow, nullable=False)` |

**Relationships:** `user`.

### `ColorMap` - `color_map`

Name mapping between LEGO and BrickLink colours.

Source: `app/models.py:85`. Fields: **3**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `lego_name` | `db.Column(db.String(100), unique=True, nullable=False)` |
| `bl_name` | `db.Column(db.String(100))` |

### `UserVote` - `user_vote`

Committed units during voting phases.

Source: `app/models.py:92`. Fields: **7**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `product_id` | `db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)` |
| `quantity` | `db.Column(db.Integer, nullable=False)` |
| `initial_quantity` | `db.Column(db.Integer, nullable=True)` |
| `phase` | `db.Column(db.String(20), default='first')` |

**Relationships:** `user`, `product`.

**Table constraints:** `(db.UniqueConstraint('user_id', 'product_id', name='uq_user_vote_product'),)`.

### `UserFavorite` - `user_favorite`

Personal campaign-specific bookmark; does not create an order.

Source: `app/models.py:109`. Fields: **5**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `product_id` | `db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)` |
| `created_at` | `db.Column(db.DateTime, default=datetime.utcnow)` |

**Relationships:** `user`, `product`.

**Table constraints:** `(db.UniqueConstraint('user_id', 'product_id', name='uq_user_favorite_product'),)`.

### `Config` - `config`

Key/value store; some keys must have annual namespace.

Source: `app/models.py:124`. Fields: **3**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `key` | `db.Column(db.String(50), unique=True, nullable=False)` |
| `value` | `db.Column(db.String(255), nullable=True)` |

### `CampaignParticipation` - `campaign_participation`

Annual enrolment, approval status and signed document for a particular campaign.

Source: `app/models.py:151`. Fields: **8**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False, index=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)` |
| `status` | `db.Column(db.String(20), nullable=False, default='pending_commitment')` |
| `signed_document` | `db.Column(db.String(255), nullable=True)` |
| `document_approved_at` | `db.Column(db.DateTime, nullable=True)` |
| `document_approved_by` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)` |
| `enrolled_at` | `db.Column(db.DateTime, nullable=False, default=datetime.utcnow)` |

**Relationships:** `user`, `campaign`.

**Table constraints:** `(db.UniqueConstraint('campaign_id', 'user_id', name='uq_campaign_participation_user'),)`.

### `Campaign` - `campaign`

Annual campaign registry, state and archive date.

Source: `app/models.py:178`. Fields: **6**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `year` | `db.Column(db.Integer, unique=True, nullable=False)` |
| `title` | `db.Column(db.String(120), nullable=False)` |
| `status` | `db.Column(db.String(20), nullable=False, default='legacy_active')` |
| `created_at` | `db.Column(db.DateTime, default=datetime.utcnow, nullable=False)` |
| `archived_at` | `db.Column(db.DateTime, nullable=True)` |

### `CampaignInsightSnapshot` - `campaign_insight_snapshot`

Campaign aggregate time series, not a billable order quantity source.

Source: `app/models.py:222`. Fields: **9**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False, index=True)` |
| `recorded_at` | `db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)` |
| `vote_cents` | `db.Column(db.Integer, nullable=False)` |
| `order_cents` | `db.Column(db.Integer, nullable=False)` |
| `vote_units` | `db.Column(db.Integer, nullable=False)` |
| `order_units` | `db.Column(db.Integer, nullable=False)` |
| `voters` | `db.Column(db.Integer, nullable=False)` |
| `buyers` | `db.Column(db.Integer, nullable=False)` |

### `ShortageWindow` - `shortage_window`

Insufficient-order extraordinary window with status/deadline; Public only.

Source: `app/models.py:239`. Fields: **8**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False, unique=True, index=True)` |
| `status` | `db.Column(db.String(24), nullable=False)` |
| `opened_at` | `db.Column(db.DateTime, nullable=False, default=datetime.utcnow)` |
| `deadline_at` | `db.Column(db.DateTime, nullable=True)` |
| `resolved_at` | `db.Column(db.DateTime, nullable=True)` |
| `opened_by` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `closing_reason` | `db.Column(db.String(120), nullable=True)` |

### `ShortageAcknowledgement` - `shortage_acknowledgement`

User- and time-specific acknowledgement of the insufficient-order notice; Public only.

Source: `app/models.py:252`. Fields: **4**.

| Field | ORM declaration |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `window_id` | `db.Column(db.Integer, db.ForeignKey('shortage_window.id'), nullable=False, index=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `accepted_at` | `db.Column(db.DateTime, nullable=False, default=datetime.utcnow)` |

**Table constraints:** `(db.UniqueConstraint('window_id', 'user_id', name='uq_shortage_ack_window_user'),)`.

## 26. Appendix: complete HTTP route map

Routes extracted from Flask decorators: **this is not a supported public REST API contract**. `POST` routes require appropriate session/authorisation, CSRF token and allowed phase. The `orders`/`products` blueprint URL prefixes are applied below. `GET / POST` routes display and process forms. When changing a route, review both the view and its tests.

### `app/main/routes.py` (55 routes)

| Method | Effective URL | Handler | Purpose |
|---|---|---|---|
| `GET` | `/` | `index` | Landing page and allowed workflow redirect |
| `GET` | `/language/<string:lang>` | `set_language` | Interface language |
| `GET` | `/dashboard` | `user_dashboard` | Participant dashboard and commitments |
| `POST` | `/vote` | `submit_vote` | Create/increase voting commitment |
| `POST` | `/favorite` | `toggle_favorite` | Toggle personal bookmark |
| `POST` | `/vote/delete` | `delete_vote` | Controlled vote removal when allowed |
| `GET` | `/dashboard/order-pdf` | `download_user_order_pdf` | Download own order PDF |
| `POST` | `/admin/campaign-archive` | `campaign_archive` | Archive validated final order |
| `POST` | `/admin/campaign-draft` | `campaign_draft` | Create next campaign draft |
| `POST` | `/admin/campaign-activate` | `campaign_activate` | Activate prepared draft when authorised/ready |
| `GET` | `/admin/campaign-readiness` | `campaign_readiness` | View annual readiness findings |
| `GET` | `/admin/campaign-history` | `campaign_history` | Archived campaign history |
| `GET` | `/admin/simulator` | `demo_simulator` | Administrator simulator |
| `GET` | `/insights` | `order_insights` | Campaign insights |
| `GET` | `/admin` | `admin_dashboard` | Administrator dashboard |
| `POST` | `/admin/products/toggle-lock` | `toggle_lock` | Lock/unlock product |
| `POST` | `/admin/products/toggle-final` | `toggle_final_status` | Change final product selection |
| `POST` | `/admin/products/promote-all` | `promote_all_products` | Bulk promote to final selection |
| `POST` | `/admin/users/toggle-access` | `toggle_user_active` | Change account access |
| `POST` | `/admin/users/toggle-admin` | `toggle_user_admin` | Change administrator role |
| `POST` | `/admin/users/validate-declaration` | `validate_declaration` | Approve signed declaration |
| `POST` | `/admin/users/delete-declaration` | `delete_declaration` | Delete declaration document |
| `POST` | `/admin/users/invalidate-declaration` | `invalidate_declaration` | Invalidate document approval |
| `POST` | `/admin/users/reset-password` | `reset_user_password` | Reset user password |
| `GET` | `/admin/users/declaration/<int:user_id>` | `download_declaration` | Download signed document |
| `POST` | `/admin/phase/activate-second` | `activate_phase2` | Start second voting phase |
| `POST` | `/admin/phase/advance-final` | `advance_phase` | Advance to final selection |
| `POST` | `/admin/phase/advance-order` | `advance_order_phase` | Release actual order phase |
| `POST` | `/admin/clean-data` | `clean_data` | See source code |
| `POST` | `/admin/test-mode` | `toggle_test_mode` | See source code |
| `POST` | `/admin/backup/create` | `create_backup_endpoint` | Create backup ZIP |
| `GET` | `/admin/backup/download` | `download_backup` | Download backup |
| `GET` | `/admin/backup/error-log` | `download_backup_log` | Download backup log |
| `POST` | `/admin/backup/restore` | `restore_backup_endpoint` | Online restore intentionally blocked: 409 |
| `POST` | `/admin/order/costs` | `update_order_costs` | Campaign tax and shipping |
| `POST` | `/admin/order/generate` | `generate_order_exports_route` | Generate final Excel and PDFs |
| `POST` | `/admin/order/regenerate` | `regenerate_order_exports_route` | Regenerate documents subject to phase rules |
| `POST` | `/admin/order/payment-details` | `update_order_payment_details` | Payment instructions and details |
| `GET` | `/admin/order/download/<string:kind>` | `download_order_file` | Download protected export |
| `POST` | `/admin/orders/update` | `admin_update_order` | Edit effective order quantities |
| `POST` | `/admin/orders/add` | `admin_add_order` | Administrator order insertion |
| `POST` | `/admin/colors/update` | `update_color_map` | See source code |
| `GET / POST` | `/admin/upload-data` | `upload_data` | Import annual catalogue |
| `GET / POST` | `/admin/upload-users` | `upload_users` | Import users |
| `GET / POST` | `/admin/campaign-draft/<int:campaign_id>/participants` | `draft_participants` | Stage draft participants |
| `GET / POST` | `/admin/campaign-draft/<int:campaign_id>/catalog` | `draft_catalog` | Stage next-year catalogue |
| `GET / POST` | `/admin/set-dates` | `set_dates` | Set campaign dates |
| `GET / POST` | `/admin/commitment` | `commitment_management` | Manage commitment PDF |
| `GET` | `/admin/audit` | `audit_dashboard` | View administrative audit |
| `GET / POST` | `/admin/settings/limits` | `manage_limits` | Edit campaign-specific limits |
| `GET` | `/admin/campaigns` | `campaign_registry` | Browse campaign registry |
| `GET / POST` | `/admin/campaigns/<int:campaign_id>/calendar` | `manage_campaign_calendar` | Configure campaign calendar windows |
| `GET / POST` | `/admin/shortage` | `shortage_admin` | Manage insufficient-order window |
| `POST` | `/shortage/acknowledge` | `shortage_acknowledge` | Acknowledge shortfall notice |
| `GET / POST` | `/shortage/increase` | `shortage_increase` | Voluntary extraordinary increase |

### `app/main/translation_admin.py` (5 routes)

| Method | Effective URL | Handler | Purpose |
|---|---|---|---|
| `GET` | `/admin/translations` | `index` | Landing page and allowed workflow redirect |
| `POST` | `/admin/translations/save` | `save` | Save translations |
| `POST` | `/admin/translations/reset` | `reset` | Reset translations |
| `GET` | `/admin/translations/export/<language>` | `export` | Export translation keys |
| `POST` | `/admin/translations/import` | `import_file` | Import translations |

### `app/auth/routes.py` (8 routes)

| Method | Effective URL | Handler | Purpose |
|---|---|---|---|
| `GET / POST` | `/login` | `login` | Log in |
| `GET / POST` | `/access` | `site_access` | Optional site access password |
| `GET` | `/logout` | `logout` | Log out |
| `GET / POST` | `/change-password` | `change_password` | Change password |
| `GET / POST` | `/profile` | `profile` | View/edit own profile |
| `GET / POST` | `/upload-declaration` | `upload_declaration` | Upload annual signed PDF |
| `GET` | `/declaration-pending` | `declaration_pending` | Check document approval status |
| `GET` | `/commitment/download` | `download_commitment` | Download document to sign |

### `orders/routes.py` (2 routes)

| Method | Effective URL | Handler | Purpose |
|---|---|---|---|
| `GET` | `/orders/` | `list_orders` | List orders |
| `GET / POST` | `/orders/create` | `create_order` | Create order when allowed |

### `products/routes.py` (2 routes)

| Method | Effective URL | Handler | Purpose |
|---|---|---|---|
| `GET` | `/products/` | `list_products` | List visible products |
| `GET` | `/products/<int:product_id>` | `product_detail` | Product detail |

## 27. Appendix: detailed service and function index

The following functions are defined in `app/services`. Underscore-prefixed internal helpers are included to explain the implementation; **do not call them from new routes without studying their preconditions**. A signature is not a stable public API contract. Search for the function/module under `tests/` and verify the full flow.

### `active_campaign.py` (61 lines)

Current campaign and annual authorisation

- `current_campaign()` - `app/services/active_campaign.py:10` - Resolve the one legacy-active campaign while excluding archived/draft years.  A draft year is never operational. Do not permit a second active campaign; activation is intentionally blocked p
- `current_membership()` - `app/services/active_campaign.py:29`
- `allowed_to_participate()` - `app/services/active_campaign.py:36`
- `require_campaign_participant()` - `app/services/active_campaign.py:44` - Reject edits to an account outside the registered campaign.  This guard must be called at the mutation boundary, including administrative edits, not just when a participant opens a page. It

### `activity_log.py` (32 lines)

Audit log of mutations

- `log_user_action()` - `app/services/activity_log.py:22`

### `annual_readiness.py` (139 lines)

Readiness checks before migration/activation

- `inspect_annual_readiness()` - `app/services/annual_readiness.py:13` - Return diagnostic findings without modifying the session or database.

### `backups.py` (215 lines)

Backups; never re-enable the online restore

- `_db_path()` - `app/services/backups.py:32`
- `_copy_sqlite()` - `app/services/backups.py:43`
- `_copy_optional_folder()` - `app/services/backups.py:52`
- `_zip_directory()` - `app/services/backups.py:63`
- `_safe_extract()` - `app/services/backups.py:72` - Unpack a trusted-format backup defensively.  Reject zip-slip paths, symlinks, duplicate names, excessive file counts, and oversized decompressed archives before touching the destination. A b
- `create_phase_backup()` - `app/services/backups.py:113` - Create a ZIP with DB + user files and record it on disk.
- `restore_backup()` - `app/services/backups.py:162` - Restore DB and files from a ZIP; force phase to manifest target.
- `write_backup_error_log()` - `app/services/backups.py:205` - Persist an error log and return its path.

### `campaign_activation.py` (88 lines)

Prepared-draft activation

- `activate_prepared_draft()` - `app/services/campaign_activation.py:13` - Promote a prepared draft without copying historical records.  This is a deliberately opt-in release gate. An administrator must enable it only after validating all application routes and Doc

### `campaign_archive.py` (164 lines)

Excel verification and annual archive

- `valid_final_workbook()` - `app/services/campaign_archive.py:20` - Require a readable XLSX workbook, not just a non-empty renamed file.
- `_finite_decimal()` - `app/services/campaign_archive.py:37` - Reject booleans, Excel formulas, non-numeric and non-finite values.
- `final_workbook_matches_order()` - `app/services/campaign_archive.py:47` - Compare the final XLSX against current campaign's authoritative order.  Reject duplicate/missing/foreign references, edited quantities/prices and totals. Excel formulas are not accepted as n
- `archive_completed_campaign()` - `app/services/campaign_archive.py:110` - Fail closed unless a finished order and its XLSX are present.  This transition is atomic with its audit record, and is idempotently rejected on repeat. Existing orders/votes are never delete

### `campaign_calendar.py` (95 lines)

Dates and non-overlapping windows

- `validate_campaign_window()` - `app/services/campaign_calendar.py:13` - Validate a campaign's configured season without imposing fixed days.  A season starts in its named year and finishes in the following year. The October-March convention is informative, not a
- `assert_no_window_overlap()` - `app/services/campaign_calendar.py:28` - Reject any shared calendar day across different annual campaigns.  Windows are inclusive: a campaign ending on a date cannot share that date with the next campaign. Missing historical dates
- `other_campaign_windows()` - `app/services/campaign_calendar.py:40` - Load configured windows of other years; reject incomplete history.
- `campaign_window_key()` - `app/services/campaign_calendar.py:51`
- `read_campaign_window()` - `app/services/campaign_calendar.py:59` - Read dates for any campaign, including archived history; never global keys.
- `configure_campaign_window()` - `app/services/campaign_calendar.py:75` - Store both dates in the same transaction; no schema migration required.  Existing archived campaigns may be inspected, but their dates are immutable.

### `campaign_data.py` (44 lines)

Filters for current campaign queries

- `active_campaign_id()` - `app/services/campaign_data.py:13` - Use the same fail-closed campaign policy as access controls.
- `products_query()` - `app/services/campaign_data.py:24`
- `orders_query()` - `app/services/campaign_data.py:28`
- `votes_query()` - `app/services/campaign_data.py:32`
- `favorites_query()` - `app/services/campaign_data.py:36`
- `validate_product_campaign()` - `app/services/campaign_data.py:40` - Prevent a foreign or unmigrated product from entering an annual order.

### `campaign_participation.py` (87 lines)

Enrolment, signed PDF and approval

- `participation_for()` - `app/services/campaign_participation.py:16` - Look up membership using *both* the campaign and user id.
- `enroll_existing_user()` - `app/services/campaign_participation.py:23` - Enrol an existing user; never inherit last year's approval.  Does not activate a campaign or grant access to legacy endpoints. Caller must commit its transaction. Unique constraint prevents
- `_require_active_membership_campaign()` - `app/services/campaign_participation.py:52` - Reject stale participation records before changing their approval state.
- `submit_signed_document()` - `app/services/campaign_participation.py:59` - New upload invalidates any prior approval; file validation is caller's job.
- `review_signed_document()` - `app/services/campaign_participation.py:72` - Approval requires an admin and an uploaded document.
- `is_eligible()` - `app/services/campaign_participation.py:84` - Never authorise based on a previous year's membership.

### `campaign_phase.py` (41 lines)

Campaign state machine

- `phase_config_key()` - `app/services/campaign_phase.py:6`
- `get_campaign_phase()` - `app/services/campaign_phase.py:15`
- `set_campaign_phase()` - `app/services/campaign_phase.py:34`

### `campaign_registry.py` (76 lines)

Annual registry and drafts

- `list_campaigns()` - `app/services/campaign_registry.py:14` - Return registered campaigns without modifying operational records.
- `register_current_campaign()` - `app/services/campaign_registry.py:19` - Record the current legacy dataset; no reset, archival or activation.  A second legacy campaign is refused because the pre-migration database cannot distinguish data from different years.
- `create_next_campaign_draft()` - `app/services/campaign_registry.py:45` - Register a future year without activating it or copying historical data.  The only permitted situation is a fully archived previous campaign and no existing draft. This does not authorize im

### `campaign_settings.py` (46 lines)

Annually namespaced configuration

- `annual_key()` - `app/services/campaign_settings.py:21`
- `get_annual_setting()` - `app/services/campaign_settings.py:29`
- `set_annual_setting()` - `app/services/campaign_settings.py:42`

### `commitment_ledger.py` (119 lines)

Commitment accounting without double counting

- `committed_total()` - `app/services/commitment_ledger.py:15` - Return conservative monetary commitment from (product_id, price, quantity).  Quantities within *one* source for a product are summed; sources are then combined using the maximum for that pro
- `effective_commitment()` - `app/services/commitment_ledger.py:59` - Calculate the active monetary commitment for a specific campaign phase.  ``order_lines`` and ``vote_lines`` contain (product_id, price, quantity). During voting all votes are binding. From t
- `materialized_order_quantity()` - `app/services/commitment_ledger.py:96` - Amount to persist for an additive order operation after the cutoff.  The first actual order must include any selected voting commitment not already represented by stored Order rows. This pre

### `declarations.py` (49 lines)

Private document files and rejection reasons

- `_issue_key()` - `app/services/declarations.py:13`
- `get_declaration_issue()` - `app/services/declarations.py:17` - Return the persistent warning shown to a user when their DJ was rejected.
- `set_declaration_issue()` - `app/services/declarations.py:22` - Store a warning message so the user knows their previous DJ was invalid.
- `clear_declaration_issue()` - `app/services/declarations.py:27` - Remove any stored warning for the given user.
- `remove_declaration_file()` - `app/services/declarations.py:32` - Delete the stored DJ file from disk and reset the DB fields.

### `draft_activation_preflight.py` (30 lines)

Next-year safety preflight

- `evaluate_draft_activation()` - `app/services/draft_activation_preflight.py:8` - Return actionable blockers for a draft; inputs are read-only snapshots.

### `draft_catalog_import.py` (100 lines)

Draft catalogue validation/import

- `validate_draft_catalog_rows()` - `app/services/draft_catalog_import.py:14` - Reject malformed Excel payloads before any database write.
- `import_draft_catalog()` - `app/services/draft_catalog_import.py:54` - Upsert by (campaign, reference), never copy or modify archived products.  Validate the entire file before making any writes. Caller must hold admin access.

### `export_path_safety.py` (20 lines)

Safe filesystem paths for exports

- `safe_export_path()` - `app/services/export_path_safety.py:5`

### `final_selection.py` (476 lines)

Ranking, selection and neutral simulation

- `get_vote_aggregates()` - `app/services/final_selection.py:35` - Return aggregate vote information per product.
- `compute_final_selection()` - `app/services/final_selection.py:65` - Evaluate (and optionally persist) the final selection respecting the given cap.  When ``persist`` is False no database writes are performed, making it safe to call from read-only contexts su
- `get_final_selection_snapshot()` - `app/services/final_selection.py:78` - Helper to obtain the current selection summary without writing to the DB.
- `get_neutral_ranking()` - `app/services/final_selection.py:83` - Return the neutral ranking list for admin review.
- `get_phase_two_selection_snapshot()` - `app/services/final_selection.py:177` - Return the ranked phase 2 selection without writing to the DB.
- `_build_neutral_row()` - `app/services/final_selection.py:182`
- `_build_neutral_scores()` - `app/services/final_selection.py:197`
- `_determine_final_selection()` - `app/services/final_selection.py:242`
- `_persist_final_selection()` - `app/services/final_selection.py:277` - Apply the computed selection to the database.
- `_fetch_promoted_ids()` - `app/services/final_selection.py:290`
- `_fetch_locked_ids()` - `app/services/final_selection.py:300`
- `_fetch_disabled_ids()` - `app/services/final_selection.py:309`
- `_fetch_voted_product_ids()` - `app/services/final_selection.py:318`
- `_iter_ranked_products()` - `app/services/final_selection.py:328`
- `_serialize_tie_candidate()` - `app/services/final_selection.py:383`
- `_determine_phase_two_selection()` - `app/services/final_selection.py:395`

### `history_summary.py` (50 lines)

Historical totals for dashboard

- `_money()` - `app/services/history_summary.py:11`
- `archived_campaign_summaries()` - `app/services/history_summary.py:17` - Return archival totals with no global, cross-year order/vote aggregations.

### `mode.py` (78 lines)

Limit rules and test mode

- `is_test_mode_enabled()` - `app/services/mode.py:22` - Return True when the admin has enabled the test mode.
- `get_limit_configuration()` - `app/services/mode.py:27` - Provide the active limits for phase/order/final selection.  Values default to the standard configuration but are overridden when the test mode flag is enabled.

### `order_exports.py` (657 lines)

Build Excel, PDFs and hashes

- `build_final_order_context()` - `app/services/order_exports.py:27` - Aggregate selected references from votes before ordering, orders afterwards.  Returns a dictionary with per-product summaries, per-user breakdowns, and the total amount contributed by the pr
- `_summary_fingerprint()` - `app/services/order_exports.py:151` - Canonical quantities in the export, independent of display ordering.  Product and participant identifiers are checked separately: identical totals distributed to different participants must
- `assert_current_export_summary()` - `app/services/order_exports.py:180` - Reject a stale or forged export summary before writing any files.
- `generate_order_files()` - `app/services/order_exports.py:186` - Persist the Excel and PDF exports for the final order.  Returns the filenames (relative to the export folder) for later download.
- `_write_excel()` - `app/services/order_exports.py:249`
- `_write_piece_pdf()` - `app/services/order_exports.py:281`
- `_write_user_pdf()` - `app/services/order_exports.py:296`
- `_write_piece_zip()` - `app/services/order_exports.py:332`
- `_write_user_zip()` - `app/services/order_exports.py:352`
- `_write_single_piece_pdf()` - `app/services/order_exports.py:392`
- `_write_single_user_pdf()` - `app/services/order_exports.py:403`
- `_append_piece_entry()` - `app/services/order_exports.py:427`
- `_append_user_document()` - `app/services/order_exports.py:467`
- `_base_pdf()` - `app/services/order_exports.py:533`
- `_download_image()` - `app/services/order_exports.py:541`
- `_build_display_name()` - `app/services/order_exports.py:561`
- `_write_line()` - `app/services/order_exports.py:570` - Helper to ensure we always start from the left margin before writing.  Avoids layout errors when the cursor is positioned near the right edge.
- `_truncate_text()` - `app/services/order_exports.py:580`
- `_safe_filename_part()` - `app/services/order_exports.py:595`
- `_format_due_date()` - `app/services/order_exports.py:600`
- `_truncate_text()` - `app/services/order_exports.py:609`
- `_resolve_product_image()` - `app/services/order_exports.py:637`
- `_create_placeholder_image()` - `app/services/order_exports.py:651`

### `order_insights.py` (187 lines)

Campaign statistics and snapshots

- `_money()` - `app/services/order_insights.py:11`
- `_product_metrics()` - `app/services/order_insights.py:15`
- `_summarize()` - `app/services/order_insights.py:31`
- `_top()` - `app/services/order_insights.py:39`
- `_groups()` - `app/services/order_insights.py:48`
- `build_insights()` - `app/services/order_insights.py:59` - Only currently active campaign; private per-user branch never exposes others.
- `capture_snapshot()` - `app/services/order_insights.py:136` - Persist actual observed figures; avoid one row per page refresh. Admin only caller.  Same-minute changes are captured on next eligible observation (or CLI with 0).
- `load_snapshots()` - `app/services/order_insights.py:160` - Only real observations: no fake backfill or synthetic daily trend.
- `yearly_comparison()` - `app/services/order_insights.py:171` - Historical campaigns use last actual observation; otherwise show unavailable.

### `order_materialization.py` (94 lines)

Synchronise selected commitment to Order

- `missing_order_floors()` - `app/services/order_materialization.py:13` - Pure planner: return {(user_id, product_id): missing_quantity}.
- `materialize_selected_commitments()` - `app/services/order_materialization.py:41` - Persist only the missing vote floor, in the current campaign.  Call at the controlled final -> order transition, after final selection has been computed. The caller owns the transaction and
- `assert_selected_commitments_materialized()` - `app/services/order_materialization.py:66` - Fail closed if any selected vote floor is absent from persisted orders.  Must run in the same transaction/snapshot as the final export. Historical votes for discarded products are intentiona

### `order_simulator.py` (167 lines)

Non-binding preview simulation

- `_eur()` - `app/services/order_simulator.py:16`
- `build_demo()` - `app/services/order_simulator.py:20` - Build reproducible fictitious end-to-end journey (no I/O).

### `quantity_rules.py` (33 lines)

Quantity steps and minimum quantities

- `validate_quantity()` - `app/services/quantity_rules.py:9` - Return (valid, human-readable explanation) for a product quantity.  Reject bool, NaN, infinity, fractional and negative quantities. Values should be loaded from validated campaign configurat

### `shortage.py` (206 lines)

Public shortage window and transactional locking

- `order_total()` - `app/services/shortage.py:17`
- `minimum_total()` - `app/services/shortage.py:23`
- `personal_total()` - `app/services/shortage.py:29`
- `user_margin()` - `app/services/shortage.py:35` - Conservative margin including selected voting floors not yet materialized.
- `window_for_active()` - `app/services/shortage.py:52`
- `open_window()` - `app/services/shortage.py:57`
- `acknowledge()` - `app/services/shortage.py:76`
- `reconcile()` - `app/services/shortage.py:92` - Idempotent worker. A reached minimum wins even at the deadline.
- `cancel()` - `app/services/shortage.py:110`
- `selected_products_for_extension()` - `app/services/shortage.py:128` - Only selected, enabled products in the current annual catalogue.
- `_add_extra_order_locked()` - `app/services/shortage.py:133` - Additive participant order during the acknowledged extraordinary window.  Fail closed on deadline, cancelled state, unsigned membership, unselected products, invalid price/quantity, material
- `add_extra_order()` - `app/services/shortage.py:200` - Atomic read-check-write boundary; roll back reserved locks on failure.

### `vote_commitments.py` (19 lines)

Non-decreasing vote validation

- `assert_nondecreasing_vote()` - `app/services/vote_commitments.py:10` - Reject invalid or decreasing quantities, including deletion (zero).

## 28. Appendix: HTML views and internationalisation

Jinja renders HTML on the server. Menus and buttons may depend on roles/phases. Before editing a template: find route-provided variables; escape user input; retain CSRF and field names; supply ES and EN translations; test each edition separately. The inventory shows templates present in this source, not every possible navigation path.

| Template | Detected heading or use |
|---|---|
| `templates/admin_audit.html` | Registro de auditoría |
| `templates/admin_campaign_calendar.html` | Calendario · campaña {{ campaign.year }} |
| `templates/admin_campaign_history.html` | Histórico de campañas |
| `templates/admin_campaign_readiness.html` | Diagnóstico de aislamiento anual |
| `templates/admin_campaigns.html` | Campañas anuales |
| `templates/admin_commitment.html` | Compromisos de campaña |
| `templates/admin_dashboard.html` | {{ _('admin.title') }} |
| `templates/admin_limits.html` | Límites de la campaña |
| `templates/admin_translations.html` | {{ _('tr.title') }} |
| `templates/auth/commitment_unavailable.html` | Compromiso pendiente |
| `templates/auth/declaration_pending.html` | Declaración jurada recibida |
| `templates/auth/login.html` | Acceso a VALBRICK |
| `templates/auth/profile.html` | Perfil de {{ current_user.username }} |
| `templates/auth/site_access.html` | Introduce la contraseña de acceso |
| `templates/auth/upload_declaration.html` | Sube tu declaración jurada firmada |
| `templates/base.html` | Vista HTML / HTML view |
| `templates/draft_catalog.html` | Importar catálogo Excel — {{ draft.year }} |
| `templates/order_insights.html` | {{ _('insights.title') }} |
| `templates/order_simulator.html` | {{ _('sim.title') }} |
| `templates/orders/create.html` | Crear nuevo pedido |
| `templates/orders/list.html` | Pedidos registrados |
| `templates/phase_info.html` | Fase Siguiente |
| `templates/products/detail.html` | {{ product.name or product.reference }} |
| `templates/products/list.html` | Listado de Productos |
| `templates/register_agreements.html` | Acepta los compromisos |
| `templates/register_details.html` | Completa tus datos |
| `templates/set_dates.html` | Configurar Fechas |
| `templates/shortage_admin.html` | Pedido insuficiente |
| `templates/shortage_increase.html` | Ampliar mi pedido durante el plazo extraordinario |
| `templates/upload_excel.html` | Subir Excel Definitivo |
| `templates/upload_users_csv.html` | {% if draft %}Preparar participantes — {{ draft.year }}{% else %}Subir CSV de Usuarios{% endif %} |
| `templates/user_dashboard.html` | {{ _('user.title') }} |
| `templates/user_order.html` | Pedido Final |

Translations come from `app/translations/es.json` and `app/translations/en.json` through `app/i18n.py`. `/admin/translations` provides save/reset/export/import; make backups and review changes before importing translations on a live server. Browser styles/scripts live under `static/` and are part of the UI; never replace server-side validation.

## 29. Appendix: test, script and procedure index

This edition has **121 `test_*.py` files**. Use the list to locate working examples before editing a subsystem. Filenames alone do not prove coverage: inspect test cases and assertions.

### Archive and backups (10)

- `tests/test_archive_multiple_years.py`
- `tests/test_archive_sqlite_guards.py`
- `tests/test_archived_participation_write_guard.py`
- `tests/test_backup_zip_safety.py`
- `tests/test_campaign_archive_action.py`
- `tests/test_campaign_archive_policy.py`
- `tests/test_iteration_67_archive_export_symlinks.py`
- `tests/test_iteration_69_archive_semantics.py`
- `tests/test_iteration_70_archive_strict_values.py`
- `tests/test_v93_offline_restore.py`

### Campaigns and years (44)

- `tests/test_active_campaign_policy_contract.py`
- `tests/test_active_campaign_registry.py`
- `tests/test_active_campaign_runtime.py`
- `tests/test_annual_catalog_import.py`
- `tests/test_annual_commitment_boundary.py`
- `tests/test_annual_export_path_safety.py`
- `tests/test_annual_financial_settings.py`
- `tests/test_annual_limit_enforcement.py`
- `tests/test_annual_limits_isolation.py`
- `tests/test_annual_participant_import_contract.py`
- `tests/test_annual_phase_isolation.py`
- `tests/test_annual_profile_catalog_scope.py`
- `tests/test_annual_readiness.py`
- `tests/test_annual_readiness_extra_tables_contract.py`
- `tests/test_annual_readiness_template.py`
- `tests/test_annual_safety_contract.py`
- `tests/test_annual_write_boundaries.py`
- `tests/test_campaign_activation_gate.py`
- `tests/test_campaign_data_consistency.py`
- `tests/test_campaign_draft_flow.py`
- `tests/test_campaign_integrity_audit.py`
- `tests/test_campaign_integrity_lifecycle_schema.py`
- `tests/test_campaign_integrity_missing_schema.py`
- `tests/test_campaign_participation_contract.py`
- `tests/test_campaign_registry_contract.py`
- `tests/test_campaign_registry_cross_state.py`
- `tests/test_campaign_registry_sqlite_indexes.py`
- `tests/test_campaign_route_scope_regression.py`
- `tests/test_draft_activation_preflight.py`
- `tests/test_draft_annual_consent.py`
- `tests/test_draft_catalog_transaction.py`
- `tests/test_draft_catalog_validation.py`
- `tests/test_draft_participant_import_route.py`
- `tests/test_export_campaign_history.py`
- `tests/test_iteration_63_campaign_integration_contract.py`
- `tests/test_iteration_64_campaign_calendar.py`
- `tests/test_iteration_65_campaign_calendar_admin.py`
- `tests/test_iteration_66_campaign_overlap.py`
- `tests/test_iteration_71_draft_atomicity.py`
- `tests/test_iteration_72_annual_consent_gate.py`
- `tests/test_prepare_campaign_columns.py`
- `tests/test_v83_multi_campaign_auto.py`
- `tests/test_v92_campaign_e2e.py`
- `tests/test_year_scope_regression.py`

### HTTP and interface (2)

- `tests/test_history_admin_ui.py`
- `tests/test_v93_release_http.py`

### Orders and exports (12)

- `tests/test_dashboard_orders_query_import.py`
- `tests/test_export_order_floors.py`
- `tests/test_export_snapshot_integrity.py`
- `tests/test_final_selection_export_scope.py`
- `tests/test_historical_order_parent_deletion.py`
- `tests/test_init_db_credentials_order.py`
- `tests/test_iteration_53_materialization_integrity.py`
- `tests/test_order_export_source.py`
- `tests/test_order_floor_materialization.py`
- `tests/test_order_materialization.py`
- `tests/test_v84_full_order_rehearsal.py`
- `tests/test_v92_export_missing_image.py`

### Other regressions (35)

- `tests/test_activation_admin_template.py`
- `tests/test_activation_cas_sqlite.py`
- `tests/test_activation_phase_atomicity.py`
- `tests/test_activation_service_transaction.py`
- `tests/test_actual_schema_bootstrap.py`
- `tests/test_compose_production_health.py`
- `tests/test_dashboard_budget_integration.py`
- `tests/test_excel_duplicate_rows.py`
- `tests/test_existing_product_scope_integrity.py`
- `tests/test_iteration_38_public_phase.py`
- `tests/test_iteration_46_public_only.py`
- `tests/test_iteration_47_sqlite_schema_contract.py`
- `tests/test_iteration_48_phase_read_integrity.py`
- `tests/test_iteration_49_selection_integrity.py`
- `tests/test_iteration_51_admin_no_delete.py`
- `tests/test_iteration_54_phase_transition_preflight.py`
- `tests/test_iteration_55_atomic_transition.py`
- `tests/test_iteration_56_transition_failures.py`
- `tests/test_iteration_57_sqlite_rollback.py`
- `tests/test_iteration_58_flask_sqlalchemy_integration.py`
- `tests/test_iteration_59_integration_contract.py`
- `tests/test_iteration_60_integration_coverage.py`
- `tests/test_iteration_61_sqlalchemy_transaction.py`
- `tests/test_license_agplv3.py`
- `tests/test_membership_reverse_integrity.py`
- `tests/test_optional_product_link_tables.py`
- `tests/test_participant_boundary_regression.py`
- `tests/test_participant_import_safety.py`
- `tests/test_private_edition_source_boundary.py`
- `tests/test_public_schedule_separation.py`
- `tests/test_run_production_default.py`
- `tests/test_simulator_v81_standalone.py`
- `tests/test_sqlite_volume_bootstrap.py`
- `tests/test_v87_maintenance.py`
- `tests/test_v88_concurrency.py`

### Security and access (10)

- `tests/test_admin_order_guard_contract.py`
- `tests/test_annual_membership_sqlite_guards.py`
- `tests/test_campaign_mutation_guard.py`
- `tests/test_campaign_write_guards.py`
- `tests/test_iteration_52_vote_entry_guard.py`
- `tests/test_iteration_62_docker_security.py`
- `tests/test_proxy_config_order.py`
- `tests/test_proxy_configuration.py`
- `tests/test_v88_http_security.py`
- `tests/test_v93_release_security_contract.py`

### Voting, limits and extensions (8)

- `tests/test_commitment_ledger.py`
- `tests/test_effective_commitment.py`
- `tests/test_iteration_50_admin_commitment_boundary.py`
- `tests/test_quantity_rules.py`
- `tests/test_v85_shortage.py`
- `tests/test_v86_shortage_increase.py`
- `tests/test_vote_commitments.py`
- `tests/test_vote_db_lock.py`

### Available scripts

- `scripts/audit_campaign_integrity.py`
- `scripts/audit_release_readiness.py`
- `scripts/backup_sqlite.py`
- `scripts/create_offline_backup.py`
- `scripts/create_offline_backup.sh`
- `scripts/export_campaign_history.py`
- `scripts/install_annual_write_boundaries.py`
- `scripts/install_archive_guards.py`
- `scripts/install_campaign_guards.py`
- `scripts/install_vote_lock.py`
- `scripts/prepare_campaign_columns.py`
- `scripts/restore_offline.py`
- `scripts/restore_offline.sh`
- `scripts/run_full_tests_isolated.sh`
- `scripts/run_v83_isolated.sh`
- `scripts/run_v84_isolated.sh`
- `scripts/run_v85_isolated.sh`
- `scripts/run_v86_isolated.sh`
- `scripts/run_v86_maintenance.sh`
- `scripts/run_v87_isolated.sh`
- `scripts/run_v87_maintenance.sh`
- `scripts/run_v87_scheduler.sh`
- `scripts/run_v88_isolated.sh`
- `scripts/run_v89_isolated.sh`
- `scripts/run_v90_isolated.sh`
- `scripts/run_v91_isolated.sh`
- `scripts/run_v92_e2e_isolated.sh`
- `scripts/run_v92_isolated.sh`
- `scripts/run_v93_release_isolated.sh`

**Maintenance sequence:** first reproduce the defect in a focused unit test, then HTTP tests, E2E, and finally the complete suite. `install_*`, `prepare_*`, `migrate_*` and `restore_*` scripts **may change persistent data or schema**: run only with instructions, verified backup, maintenance window and rollback plan. `run_*_isolated.sh` scripts are meant for disposable environments.

## 30. Edition source references and limitations

**Inspected baseline:** VALBRICK Public V93-RC1 (2026-11-01). Extracted from **13 ORM models**, **72 routes**, **27 non-empty service modules containing **129 declared functions**, **33 HTML templates** and **29 scripts. These inventories were produced by syntactic analysis; they are not a production audit or proof of full branch coverage. Regenerate and review after source changes.

**Source concordance:** keep this handbook alongside the exact edition source ZIP. `docs/DESPLIEGUE.md`, `docs/RECUPERACION.md`, `README.md`, `LICENSE`, `NOTICE` and `SECURITY.md` are primary installation references. If this handbook contradicts versioned source, pause, verify the implementation, and update the documentation before manipulating real data.

**Production acceptance still required:** real domain/TLS setup, visual browser acceptance, recovery from an external backup on the destination server, persistent storage permissions, and pinned dependencies. This document is not V1.0 certification; release approval requires those checks and operational ownership.

