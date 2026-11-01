# VALBRICK | Public | Administrator manual

**V93-RC1**  |  **2026-11-01**  |  **AGPL-3.0-only**  |  **VALBRICK**

> Based on the inspected source files of the validated edition. Release candidate; not a production certification.

---

## Scope, authority and cautions
This manual describes **VALBRICK Public** operational procedures for V93-RC1. Administrators manage people, catalogues, phases, costs and orders with real-world consequences. Passing automated tests does not replace HTTPS deployment or human acceptance checks.

**Non-negotiable rules:** never use production data in `isolated`, never restore a database while Flask is running, never publish signed documents on GitHub, and never mix Public and Extended source. An archived campaign cannot simply be reopened via the interface.

## 1. Roles and initial checks
1. Confirm the `EDITION` file says `PUBLICA`, and check the operational year on screen.
2. Log in through the site access gate and administrative account. Only users with `is_admin` may access `/admin` and manage orders for other users.
3. Review production settings: HTTPS, secret key, initial passwords, AGPL source link, proxy and persistent volume. The programming manual lists exact configuration keys.
4. Before any import or edit, create and download a backup. Keep another copy off-server.
5. Do not use **test mode** for real purchasing: it changes limits and some business semantics. Make sure it is clearly disabled before using real data.

## 2. Administration dashboard
Major sections include **Products, Ranking, Users, Colours, Orders and Logs**. Other pages cover **Campaigns**, **Annual readiness**, **Calendar**, **Audit**, **Limits**, **Translations**, **Insights** and **Simulator**. Phase changes are form buttons: read their label and current state carefully.

**Dashboard rule:** an HTTP redirect after submitting a form does not prove the operation succeeded. Always review the success/error flash message and the resulting records.

## 3. Import participants from CSV
Page: `/admin/upload-users`. Files must use **UTF-8** and contain a header with required `username,password` columns. Other recognised columns include `first_name,last_name,dni,active,agreements,agreements_accepted,paid,declaration`.

```csv
username,password,first_name,last_name
person_01,UNIQUE_TEMP_PASSWORD_01,Ana,Example
person_02,UNIQUE_TEMP_PASSWORD_02,Luis,Example
```

**Fictional example only.** Never commit a CSV containing passwords or personal data. Imports reject `is_admin`, duplicate headers and accidental edits to administrator accounts. Existing identities from older campaigns are not meant to have passwords or old approvals overwritten: annual membership resides in `CampaignParticipation`. New users must change initial credentials.

When preparing a new year's draft, use the **draft participant** import page, not the current campaign's import. Identities and approvals must not be silently carried forward.

## 4. Commitment PDF and approval
1. Open **Commitment management** (`/admin/commitment`) and upload or configure the official document for the current year.
2. Verify it is downloadable from a non-admin test account via `/commitment/download`.
3. Participants download, sign and upload their PDF. The dashboard provides **Validate declaration**, **Invalidate declaration** and, where permitted, document deletion controls. Review the actual content, not just the extension.
4. Approval belongs to the active year. An older archived approval does not automatically authorise the next campaign.
5. Signed PDFs contain personal data: avoid publishing them in backups, commits, issues or support messages.

## 5. Import the Excel catalogue
Page: `/admin/upload-data`. Use an `.xlsx` with a header and a reference column such as **Material**, **Communication number** or `reference`; provide **Description** or `name`. Recognised price aliases include `2026_prices_in_eur`, `2025_prices_in_eur` and `price`, plus colour, image and group columns.

| Material | Description | 2026_prices_in_eur | colour_id |
|---|---|---:|---|
| 300100 | Fictional red part | 1.00 | 5 |
| 300101 | Fictional blue part | 2.00 | 1 |

**Review the import report:** imported prices, duplicate references, colours, rejected lines and differences from the prior catalogue. Changing prices after commitments have been recorded affects totals and limits; perform a backup, human review and integrity checks. The draft import page is `/admin/campaign-draft/<id>/catalog` and validates the whole input before writing.

## 6. Order lifecycle phases
| Internal phase | Administrative action | Main prerequisite |
|---|---|---|
| `first` | Open second phase | Active campaign in first phase. |
| `second` | Advance to final selection | Check minimum and ranking. |
| `final` | Resolve selection, release orders | No pending ties, no excess references, non-empty selection. |
| `order` | Confirm quantities and export | Selected commitments materialised into `Order`. |

Transitions use `/admin/phase/activate-second`, `/admin/phase/advance-final` and `/admin/phase/advance-order`. `final -> order` recomputes selection, materialises accepted quantities and changes phase as a single transaction, rolling everything back on failure. Automatic phase backups **may fail without blocking the transition**: if you see a backup error, create another backup and download its error log.

## 7. Ranking and product management
In **Ranking** verify selected, locked and excluded references, their position, votes and euro totals. The ordinary final selection limit defaults to 85, but it is configurable per campaign and test mode overrides it. Ties and over-limit references prevent order release. Do not choose **Promote all** without reviewing the effect.

In **Products** check reference locking, names, codes, colour, prices and voting restrictions. Historical records are protected; deleting users or products with existing orders is not an acceptable cleanup method.

## 8. Limits, dates and calendar
`/admin/settings/limits` changes the annual limits made editable by the UI, including collective minimum, personal budget and final selection count. Other reference caps originate from `config.py` and are not all editable in the annual form. **Do not assume every configuration value is annual.**

Dates can be set through `/admin/set-dates` and `/admin/campaigns/<id>/calendar`, subject to overlap checks. Changing a calendar after voting starts requires attention to the actual state, server time zone and any external snapshot/reconciliation scheduler. Record the change.

## 9. Final order creation and archive
1. Reach `order` from `final` using the release button; **Generate order** must be disabled beforehand.
2. Verify materialised selected quantities and totals. Do not add `UserVote` and `Order` together: after materialisation, orders are authoritative for exports.
3. Review the collective minimum (campaign-specific; code default **EUR 4,800**) and personal ceilings. Outside test mode, an order below minimum cannot be exported directly.
4. Configure tax and shipping. Validate IBAN and a future payment due date where necessary.
5. Select **Generate order**. The code saves `final_order_generated_at`, generates the definitive Excel workbook and two ZIP bundles containing per-reference and per-user PDFs; combined PDFs are also written internally.
6. Download files through **Orders** and open sample PDFs, including items without an image. Reconcile references, quantities, prices, tax and shipping.
7. After finalisation ordinary edits are locked. Regeneration may produce updated files after changing payment details: inspect logs and never confuse a background-job-start message with confirmed completion.

**Archiving:** `/admin/campaign-archive` requires the confirmed active year, a compatible order phase, the export timestamp and a valid Excel file. It strictly compares references, amounts, prices and quantities with authoritative orders. Editing the spreadsheet manually invalidates archiving.

## 10. Public-only: insufficient order
If the actual `Order` total is below the configured minimum, open `/admin/shortage`. You can **Open extraordinary window** for 1-30 days. The notice reaches eligible participants, who must acknowledge it before increasing eligible selected quantities within their remaining budgets.

Select **Reconcile now** to update the state. `reconcile()` closes the window as reached when the minimum is met and can cancel it upon expiry. Expiry does not magically trigger a change if no request or external worker runs: schedule reconciliation if you need unattended handling. Manual cancellation requires typing `CANCELAR` and does not erase archived orders. Do not produce the definitive workbook while the normal-mode minimum remains unmet.

This edition has neither `FinalExtensionInterest` nor private-invitation endpoints. Do not follow Extended procedures here.

## 11. Annual archive, draft and next-year preparation
1. Download the definitive Excel and PDF bundles, and verify the corresponding server files exist.
2. Under **Campaigns**, archive the active period and confirm **the exact year** requested. Historical rows are retained.
3. Only after archiving may you create a later-year draft. `draft` is a preparation state, not an operational campaign merely because a record exists.
4. Import the draft catalogue and draft participants, without reviving old enrolments by accident.
5. Open `/admin/campaign-readiness` and annual audits. Resolve inconsistent tables, permissions, documents, missing-year records and overlapping periods before activation.
6. Draft activation has additional transactional validation. If preflight fails, **do not bypass it with manual SQL**.

**Maintainer caution:** some backward-compatibility comments remain in the code. New-year workflows require dedicated readiness review even when the annual scenario tests pass. Do not claim universal migration support for arbitrary old databases without a rehearsal.

## 12. Backups and actual recovery
**Web administration:** `Create manual backup`, `Download backup` and `Download error log`. An old **Restore** control may remain in the template for compatibility, but `/admin/backup/restore` returns **409** and must not be used.

**Offline backup:** from the deployment directory, after stopping external tasks that write to SQLite:

```sh
sh scripts/create_offline_backup.sh
```

**Restore a complete ZIP:** retain a separate external backup, stop schedulers and run:

```sh
sh scripts/restore_offline.sh ./data/backups/BACKUP_FILENAME.zip
```

The procedure stops the container, validates the ZIP and SQLite, checks the source edition and retains `data.pre-restore-*`. If it fails, do not restart blindly: inspect logs and state; verify the campaign and documents before reopening access. Follow `docs/RECUPERACION.md`.

## 13. Diagnostics and audit pages
- `/admin/audit`: investigate campaign integrity findings.
- `/admin/campaign-readiness`: requirements report for another year; diagnostic rather than independent authorisation.
- `/admin/campaign-history`: read-only historic view, not an editor for old orders.
- `/admin/simulator`: illustrative figures, never treat as participant commitments.
- `/admin/translations`: edit permitted translation keys; import/export JSON, with overrides in `/data/translations`.
- `docker compose logs --tail=80 app`: application and container logs.

For a reproducible issue capture: date, campaign year, phase, endpoint, action, expected result, observed result, sanitised log and the specific release package.

## 14. Secure server operations
- Docker uses `./data:/data`, non-root UID 10001 and appropriate permissions. `.env` secrets never belong in source control.
- Keep the container bound to `127.0.0.1:5001` and place a trusted HTTPS proxy in front. Set `TRUSTED_PROXY_COUNT` only when the proxy sanitises forwarded headers.
- Point `SOURCE_CODE_URL` to the corresponding code of **this edition**, as required for AGPL source access.
- Before upgrades, take external backups, test in `isolated`, assess schema changes, run `docker compose up --build -d`, and inspect status and logs. **Never use `docker compose down -v`** against valuable data.
- Establish backup rotation/retention, disk monitoring, dependency security review and certificate renewal checks.

## 15. Manual acceptance rehearsal
| Case | Expected result |
|---|---|
| Temporary user logs in | Must change password before normal use. |
| Annual signed document | Pending until approved; previous year's approval is not reused. |
| CSV and Excel into fictional environment | No privilege escalation or reference duplication. |
| `final` with unresolved tie | Cannot release orders. |
| `order` after valid final selection | Generate order button enabled; orders materialised. |
| Excel and PDF bundles | Downloads open and totals reconcile. |
| Edited Excel | Archive is rejected. |
| Valid yearly archive | Status `archived`, history preserved. |
| New draft | No inherited votes or orders. |
| Web restoration | HTTP 409 with no mutation. |
| Offline restoration | Prior data retained; recovery rehearsed. |

## 16. Administrator sign-off checklist
- [ ] Correct `EDITION`, year, server and domain verified.
- [ ] Test mode disabled; limits, dates, catalogue and documents reviewed.
- [ ] Users approved for **this** year; consent recorded.
- [ ] Final selection resolved; effective quantities reconciled.
- [ ] This edition's special procedure finished before export.
- [ ] Excel, PDF/ZIP and payment details checked.
- [ ] Local and external backups; test restore completed.
- [ ] Annual audit clean and history retained.
- [ ] HTTPS, filesystem permissions, server security and AGPL source link checked.

## Source references
`app/main/routes.py`, `app/auth/routes.py`, `app/services/campaign_phase.py`, `app/services/campaign_settings.py`, `app/services/final_selection.py`, `app/services/order_materialization.py`, `app/services/order_exports.py`, `app/services/campaign_archive.py`, `app/services/backups.py`, `docs/DESPLIEGUE.md` and `docs/RECUPERACION.md`. See the programming handbook for architecture, contracts and tests.

