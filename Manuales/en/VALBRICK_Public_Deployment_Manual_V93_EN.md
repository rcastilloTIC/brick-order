# VALBRICK Public Edition

**Deployment and server operations manual**  
**Documented release:** V93-RC1 · November 1, 2026  
**Edition:** PUBLIC · Own-source license: GNU AGPL-3.0-only  
**Project attribution:** VALBRICK (pseudonym)

> **Purpose.** This manual explains how to publish the source code, prepare a Linux server, configure Docker and HTTPS, start the Public edition, verify operation, and perform backups, restores and upgrades. Its instructions were checked against the actual `VALBRICK_Publica_V93.zip` distribution. They do **not** apply to the Extended edition or certify a deployment that has not yet been tested on your server.

> **Release status.** V93-RC1 passed the author's reported isolated Docker suites (532 tests, 167 subtests, zero failures). That evidence does not replace checking your actual DNS, HTTPS, filesystem permissions, backups, recovery and browser workflows. Do not process real participants' documents before completing the acceptance checklist in this manual.

## 1. What are you deploying?

VALBRICK Public is a Flask web application for LEGO group orders. It manages yearly participant enrollment and approval, the catalog, voting, final product selection, orders, Excel/PDF generation and archived campaign history. The **Public** edition handles insufficient-order workflows through a public notice and extraordinary increases. It **does not** implement the voluntary private extension rounds of Extended.

Recommended architecture:

```text
User browser (HTTPS)
       |
       v
Domain DNS -> Caddy on the SERVER (public ports 80 and 443)
       |
       v
127.0.0.1:5001 -> Docker Compose -> Gunicorn -> Flask VALBRICK
                                      |
                                      v
                            ./data (persistent)
                            db/app.sqlite
                            declarations/
                            exports/
                            backups/
```

The `Dockerfile` uses Python 3.11, **one Gunicorn worker**, and an unprivileged process running as **UID/GID 10001**. `docker-compose.yml` publishes the internal port 5001 **only** on the server's loopback interface. The host's `./data` directory survives container replacement.

## 2. Choose an environment and check prerequisites

**Reference scenario:** an Ubuntu LTS Linux server/VPS with Docker Engine, the Docker Compose plugin, and **Caddy installed on the host**. Adapt operating-system and networking instructions if you use another platform, another reverse proxy, or Docker Desktop.

You will need:

- Administrator access over SSH, an account authorized to manage Docker, and sufficient free space for the SQLite database and generated documents.
- A domain name you control, with DNS A/AAAA records pointing to the correct server.
- Public TCP ports **80 and 443** open to Caddy; do **not** expose port 5001 on the public firewall.
- Git to obtain the repository. Host-side Python 3 is optional and is used only to generate secret values; Flask itself runs inside Docker.
- A separate location for protected or encrypted off-server backups and a defined retention policy.

Harden SSH, keep the operating system updated, and preserve SSH access before changing firewall rules. **Membership in the Linux `docker` group grants root-equivalent control** over the host; restrict it to trusted operators.

## 3. Verify the correct distribution

Use **VALBRICK Public V93-RC1 only**. The extracted root directory should contain:

| File/directory | Purpose |
|---|---|
| `EDITION`, `VALBRICK_EDITION` | Identifies the distribution; must indicate `PUBLICA`. |
| `Dockerfile`, `docker-entrypoint.sh` | Build instructions and container entry point. |
| `docker-compose.yml` | The `app` service, port binding, environment and persistent bind mount. |
| `.env.example`, `.gitignore`, `.dockerignore` | Sample environment and exclusions. |
| `Caddyfile.example` | Host-based HTTPS reverse proxy example. |
| `app/`, `products/`, `orders/`, `templates/`, `static/` | Application source and views. |
| `scripts/`, `tests/` | Validation and maintenance tools. |
| `LICENSE`, `NOTICE` | Open-source license and attribution. |

```sh
cat EDITION
# Expected: PUBLICA
ls -la .env.example docker-compose.yml Dockerfile LICENSE NOTICE
```

Never mix in an Extended checkout, old installations, `isolated/` test trees, actual participant documents or production databases. **The application ZIP is not a backup of operational data.** Maintain backups separately.

## 4. Publish the Public source code on GitHub

If an independent Public repository already exists, inspect both its current files and Git history. Otherwise create a new, empty **public** GitHub repository without an initial README, then run the following **in the directory containing Dockerfile**:

```sh
git init
git branch -M main
git config --local user.name "VALBRICK"
# Replace this placeholder with YOUR noreply address from GitHub > Settings > Emails.
git config --local user.email "YOUR_GITHUB_NOREPLY_ADDRESS"
git add .
git status --short
git diff --cached --name-only
git commit -m "VALBRICK Publica V93-RC1"
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
```

**Review before committing:** `.env`, `data/`, `*.sqlite`, signed declarations, participant PDFs, backup ZIPs, `.key` files and Extended source must not be present. If a secret has been published previously, **remove it, rotate it and review the repository history**. `.gitignore` does not erase old commits.

Keep corresponding Public source publicly available as required by AGPLv3 for applicable network use. Later set `SOURCE_CODE_URL` to the exact HTTPS repository address, preferably an identifiable tag or immutable commit. Do not label an unaccepted deployment as V1.0.

## 5. Install and verify Docker

Follow the official Docker Engine and Compose plugin installation guide for your Linux distribution; for Ubuntu use <https://docs.docker.com/engine/install/ubuntu/>. Avoid unreviewed third-party installation scripts. Verify:

```sh
docker --version
docker compose version
docker info
```

If your account lacks Docker permissions, use an authorized administrative workflow. The remaining examples assume that `docker compose` is available to the operator. Make sure no unrelated service uses the host's port 5001:

```sh
sudo ss -ltnp | grep ':5001' || true
```

There is **no need to install Flask, Gunicorn or pytest on the server host**. Python dependencies are installed into the container image. `requirements.txt` currently uses allowed version ranges rather than a comprehensive lock file; record and review the versions resolved in the tested image before calling a deployment reproducible.

## 6. Obtain the repository in a stable directory

Once the public repository exists:

```sh
cd ~
git clone https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git valbrick-public
cd ~/valbrick-public
cat EDITION
# Must print PUBLICA
```

Alternatively, upload and extract the release ZIP into a **new** server directory, without overwriting an existing deployment or mixing editions. Unless otherwise noted, subsequent shell commands must run **from the project root**, `~/valbrick-public` in this example.

## 7. Configure `.env` and generate secrets

A private `.env` file is required. Never commit it to GitHub or attach it to a public support ticket.

```sh
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
# Edit values with: nano .env
```

Replace every `REPLACE_...` placeholder. The following is a **template, not a set of passwords**:

```dotenv
FLASK_ENV=production
ADMIN_USERNAME=admin
ADMIN_PASSWORD=REPLACE_WITH_UNIQUE_PASSWORD_OF_16_PLUS_CHARACTERS
DEFAULT_USER_PASSWORD=REPLACE_WITH_DIFFERENT_UNIQUE_PASSWORD
SECRET_KEY=PASTE_64_RANDOM_HEXADECIMAL_CHARACTERS_HERE
SITE_ACCESS_PASSWORD=REPLACE_WITH_DIFFERENT_LONG_PASSPHRASE
PORT=5001
TRUSTED_PROXY_COUNT=1
SOURCE_CODE_URL=https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY
```

| Setting | Effect and recommended handling |
|---|---|
| `FLASK_ENV` | Use `production` to enable configuration checks and disable debug mode. |
| `SECRET_KEY` | Signs Flask sessions; generate at least 32 bytes of randomness and preserve it securely. |
| `ADMIN_USERNAME` | Administrator username created if missing. |
| `ADMIN_PASSWORD` | Initial administrator password; startup requires at least 12 characters, and 16+ is recommended. |
| `DEFAULT_USER_PASSWORD` | Initial password when participants are created/imported; use a different value from the admin password. |
| `SITE_ACCESS_PASSWORD` | Additional site-entry passphrase before the user login. |
| `PORT` | Host-side loopback port (default 5001); the container listens internally on 5001. |
| `TRUSTED_PROXY_COUNT` | Set to `1` **only** with one trusted Caddy proxy that sanitizes the `X-Forwarded-*` headers; otherwise use `0`. |
| `SOURCE_CODE_URL` | Public HTTPS URL for the **Public edition's corresponding source code**; mandatory in production. |

**Important:** `ADMIN_PASSWORD` is used when the initial admin record is created. Editing this variable on an **existing** database does **not** automatically reset that account's stored password. Use the supported account-management process instead.

The Compose file already enforces `SESSION_COOKIE_SECURE=true`, so browsers must access the deployed site through HTTPS to send session cookies. Do **not** weaken this to enable public HTTP logins. `config.py` also supports optional settings (such as `REDIS_URL`, campaign limits and languages); test changes before deployment.

## 8. Prepare persistent storage and permissions

Docker Compose mounts `./data` on the host at `/data` inside the container:

```sh
mkdir -p data/db data/declarations data/exports data/backups
sudo chown -R 10001:10001 data
ls -ld data data/db data/declarations data/exports data/backups
```

UID/GID 10001 comes from the actual `Dockerfile`. The application must be able to write its database and the signed declarations, exports and backups:

```text
valbrick-public/
  .env                  # PRIVATE - never publish
  data/                 # PRIVATE - never publish
    db/app.sqlite       # operational SQLite database
    declarations/       # signed participant files
    exports/            # Excel and PDF output
    backups/            # recovery ZIPs and other backups
```

**Do not confuse** `data/db/app.sqlite`, the live database, with `database.sqlite3`, the copy of that database **inside an offline backup ZIP**. Retain `data/` across upgrades. If logs show `Permission denied`, check the bind mount, ownership and UID before restarting.

## 9. Validate Compose configuration and start

From the project root:

```sh
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 app
```

On the first startup, `run.py` builds the Flask application, initializes database tables and creates an administrator if absent. A missing `SECRET_KEY`, site access password, valid source URL or initial admin password should cause startup to **fail fast**, with diagnostic information in the container logs.

Verify the backend is only available locally:

```sh
docker compose ps
sudo ss -ltnp | grep ':5001'
# Local connectivity only; do not attempt a normal sign-in over HTTP:
curl -I http://127.0.0.1:5001/access
```

A `200` or redirect may be expected depending on route/session. This establishes backend connectivity; it does **not** prove HTTPS or full application correctness. Compose's healthcheck only opens a TCP socket: `healthy` does not prove that login, exports or database writes work.

Never change the port mapping from `127.0.0.1:${PORT:-5001}:5001` to `0.0.0.0:5001:5001`. That would expose Gunicorn directly to the Internet without the intended TLS proxy.

## 10. Configure Caddy and public HTTPS

This guide assumes **host-installed Caddy**, not a separate Caddy container. Install it following <https://caddyserver.com/docs/install>. With correct DNS, accessible public ports 80/443 and persistent Caddy state, it can obtain and renew certificates automatically.

Replace the domain and set `/etc/caddy/Caddyfile` to:

```caddyfile
orders.example.com {
    reverse_proxy 127.0.0.1:5001
}
```

Validate and reload Caddy:

```sh
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy
curl -I https://orders.example.com/access
```

`orders.example.com` is a placeholder, **not** a real deployment URL. Set DNS A (and AAAA if using IPv6) records to the server, allow incoming 80/443 and keep 5001 private. If Caddy runs in another container, its `127.0.0.1` does **not** mean the application host; this architecture must be adapted before deployment.

When Caddy is the sole trusted proxy, `TRUSTED_PROXY_COUNT=1` lets Flask use sanitized forwarded headers. Do not increase the count without examining the full proxy chain. See <https://caddyserver.com/docs/automatic-https> for TLS prerequisites and troubleshooting.

## 11. Verify the first browser session

Open **`https://YOUR_DOMAIN/`**, not the backend's unencrypted address. The expected user journey is:

1. **Site access** form using `SITE_ACCESS_PASSWORD`.
2. VALBRICK **login** using `ADMIN_USERNAME` and the initial admin password.
3. Administrator dashboard and annual campaign registration/activation.
4. Participant records, signed documents, catalog, campaign limits and schedule, following the administrator manual.
5. Final selection, move to `order` phase, **Generate/Place order** (`Realizar pedido`) button, Excel/PDF export, yearly archive and history.

First use **fictitious** participants and documents. Confirm the footer links to the Public source configured in `SOURCE_CODE_URL`. You should not see voluntary private invitation and extension features: those belong to Extended. Record the tested URL, date, version, operator and result. Test from an external browser, not just the server itself.

## 12. Run the isolated automated suites

Run tests in a **separate clone or isolated directory**, not in production storage. These Docker scripts use disposable containers with no production `./data` bind mount and no published service ports:

```sh
sh scripts/run_v93_release_isolated.sh
sh scripts/run_v92_e2e_isolated.sh
sh scripts/run_full_tests_isolated.sh
```

The author's last reported Public V93-RC1 full suite resulted in **532 passing tests, 1 skipped, 167 passing subtests and zero failures**. This is historical evidence, not a guarantee about a newly rebuilt image with potentially different dependency versions. Preserve test results alongside the deployed Git commit and container image information.

Even extensive unit tests do not establish DNS correctness, HTTPS certificate validity, firewall rules, restored data, real browser usability or host filesystem permissions.

## 13. Create recoverable full backups

You can still **create and download** backups through the administrator interface. For an offline, verified full backup while the web service is stopped, run from the project root:

```sh
sh scripts/create_offline_backup.sh
```

This script warns you to stop external schedulers, stops the `app` service, creates and verifies a ZIP in `data/backups/`, and restarts the service **only on success**. On failure, the application **remains stopped** for investigation. The ZIP contains `manifest.json`, `database.sqlite3`, `declarations/` and `exports/` as present.

**A stand-alone SQLite copy is not a complete order backup.** Signed declarations and generated output live in separate directories. Copy every full backup to protected storage **outside the same server**, control access (backups may contain personal data), and rehearse restorations periodically in a disposable instance. Offline ZIPs may be owned by UID 10001 with file mode `0600`; use authorized administrative access when copying them without weakening general file permissions.

## 14. Restore with the application stopped

**Web-based restoration is disabled** in V93-RC1. Do not re-enable it as a shortcut. To restore a complete backup:

1. Select the correct **Public** ZIP, inspect its origin, and first rehearse in an isolated installation.
2. Stop any external `cron`/scheduler that may write to SQLite or documents. Stopping the web container does not stop external jobs.
3. Place the ZIP inside the project, e.g. `./data/backups/`, and make it available to the restore process. If the directory is owned by UID 10001, administrator privileges may be necessary to copy it. For example:

```sh
sudo cp /SAFE_PATH/BACKUP_PUBLIC.zip ./data/backups/
sudo chown 10001:10001 ./data/backups/BACKUP_PUBLIC.zip
sudo chmod 600 ./data/backups/BACKUP_PUBLIC.zip
```

4. Execute from the project root:

```sh
sh scripts/restore_offline.sh ./data/backups/BACKUP_FILE_NAME.zip
```

The script stops `app`, validates the ZIP, manifest, SQLite integrity, edition and phase, stages the replacement tree and supports rollback if the directory swap fails. On success, the previous data tree is retained as `data.pre-restore-DATE/`. On failure, **the application remains stopped**; inspect the error before attempting a restart.

Afterwards check campaigns, participants, orders, references, Excel/PDF output and archived history. Keep `data.pre-restore-*` until you have validated recovery and obtained an external backup. An **Extended** ZIP must never be restored into Public; the validation rejects it.

## 15. Upgrade and roll back safely

Do not overwrite a running deployment with a new ZIP. Use a conservative, documented change process:

1. Schedule a maintenance window and confirm that an external, recent full backup exists.
2. Test the target commit in a **separate installation** with fictitious data; review schema and dependency changes.
3. Create another offline full backup immediately before upgrading.
4. Stop the application, switch to a **reviewed and tested** commit/tag, rebuild and verify logs.

```sh
sh scripts/create_offline_backup.sh
# First verify the target commit/tag in a different checkout.
docker compose stop app
git status --short
git fetch --tags
git checkout TESTED_COMMIT_IDENTIFIER
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 app
```

The checkout command is an **example** for a clean Git working tree and an already tested commit; do not discard local modifications. If an upgrade changed the SQLite schema, rolling back **only the application source** may be unsafe. Restore the matching **code + data** combination from the earlier release and backup, then validate before reopening to users.

Never run `docker compose down -v` or delete `data/` as if it were a cache directory. Record each change's date, commit hash, verified backup and test results.

## 16. Scheduled maintenance and operational limits

The packaged `docker-compose.yml` defines **only** the `app` service. It does **not** deploy a separate scheduler. Flask exposes `check-shortage` and `capture-insights`, combined in `scripts/run_v87_maintenance.sh`; periodic execution requires an external scheduler configured and supervised by the operator.

Do **not** run two schedulers concurrently or run maintenance outside the correct application environment/database. If you add cron or another service, document the owner, interval, logs and stop procedure before backups/restores. The included `run_v87_scheduler.sh` is intended to execute **inside a configured container**, not on the bare host.

Keep Gunicorn at **one worker** unless database concurrency and request rate limiting are reassessed. The application uses SQLite and defaults to a process-local `memory://` rate-limit backend, not a shared multi-worker store. Monitor storage (`df -h`, `du -sh data`), container status, logs and the age of off-server backups.

## 17. Minimum security requirements

- Use strong, separate secrets and HTTPS; apply operating-system updates and keep `.env` out of Git.
- Never publish live SQLite databases, identity data, signed forms, export files, backup ZIPs or logs containing personal details.
- Reserve port 5001 for the **local host**; only the reverse proxy's ports 80/443 should be internet-accessible.
- Use `TRUSTED_PROXY_COUNT=1` only for a trusted proxy that normalizes forwarded headers.
- Restrict Docker and SSH access; enable GitHub secret scanning and dependency alerts.
- Python requirements are expressed as **version ranges**, not a complete lock; re-test images when dependencies change.
- Store backups outside the server, restrict access, and rehearse end-to-end recovery.
- Preserve AGPL-related `LICENSE`, `NOTICE` and access to the corresponding source revision.

## 18. Troubleshooting reference

| Symptom | Possible cause | What to check |
|---|---|---|
| `docker: command not found` | Docker not installed | Install Engine and Compose using official instructions. |
| Docker permission denied | Operator cannot access daemon | Use an approved admin workflow; `docker` group gives privileged access. |
| `/data/... Permission denied` | Bind mount inaccessible to UID 10001 | Check host `./data`, ownership and permissions. |
| Application exits during startup | Incomplete `.env` or incompatible DB | `docker compose logs --tail=100 app`; check secrets and `SOURCE_CODE_URL`. |
| HTTPS returns `502 Bad Gateway` | Caddy cannot reach Gunicorn | Check `docker compose ps`, loopback port 5001 and Caddyfile. |
| No TLS certificate | DNS/ports 80/443 misconfigured | Inspect A/AAAA records, firewall and Caddy logs. |
| Incorrect scheme/redirect | Forwarded proxy headers | Verify trusted Caddy and `TRUSTED_PROXY_COUNT`. |
| Login fails only over HTTP | Secure session cookie | Access via `https://YOUR_DOMAIN` instead of disabling HTTPS. |
| No active yearly campaign | Campaign registry not prepared | Complete annual administrator setup. |
| Participant creation/import returns 503 | Missing/insecure `DEFAULT_USER_PASSWORD` | Set securely in `.env`, restart without revealing secret. |
| Order export unavailable | Wrong phase or validation | Check `order` phase, dashboard notices and logs; do not bypass checks via SQL. |
| Offline backup failed | External writer, disk, permissions | Stop external jobs, inspect storage and errors; script leaves `app` stopped. |
| Restore rejected | Wrong, corrupt or Extended backup | Supply a valid matching ZIP and examine the validation error. |

Initial diagnostic commands:

```sh
docker compose ps
docker compose logs --tail=100 app
sudo systemctl status caddy
sudo ss -ltnp | grep -E ':(80|443|5001)\b'
df -h
```

Never paste full production logs or `.env` into a public issue without carefully removing sensitive information.

## 19. Acceptance checklist before real users

Record your evidence for **this specific server**:

- [ ] Public-only repository contains the complete open source, `LICENSE` and `NOTICE`.
- [ ] Git commit and Docker image correspond to the release that was tested.
- [ ] `.env` has strong separate secrets, the actual `SOURCE_CODE_URL` and `FLASK_ENV=production`.
- [ ] `data/` persists, belongs to UID 10001 and is absent from GitHub.
- [ ] Port 5001 is bound to `127.0.0.1`, not a public interface.
- [ ] Public domain serves valid HTTPS; Caddy runs as a managed service.
- [ ] Site passphrase, administrator login and navigation work in an external browser.
- [ ] Fictitious campaign: participant, declaration, selection, order, Excel/PDF and history all work.
- [ ] Order export button is enabled only in the correct phase.
- [ ] Isolated V93, E2E and full test suites pass for the deployed revision.
- [ ] A full ZIP backup is stored off-server and restored successfully in rehearsal.
- [ ] Upgrade/rollback is documented and external schedulers are stopped for restores.
- [ ] SSH/firewall, disk space and backup retention policy have been checked.

**Release decision:** until these checks pass on the actual host, call this **V93-RC1 release candidate**, not a production-certified V1.0.

## 20. File map and reference sources

**Verified application files:** `README.md`, `.env.example`, `config.py`, `run.py`, `app/__init__.py`, `Dockerfile`, `docker-entrypoint.sh`, `docker-compose.yml`, `Caddyfile.example`, `docs/DESPLIEGUE.md`, `docs/RECUPERACION.md`, `scripts/create_offline_backup.sh`, `scripts/create_offline_backup.py`, `scripts/restore_offline.sh`, `scripts/restore_offline.py`, `scripts/run_v87_maintenance.sh`, `scripts/run_v93_release_isolated.sh`, `scripts/run_v92_e2e_isolated.sh`, `scripts/run_full_tests_isolated.sh`, `.gitignore`, `.dockerignore` and `.github/workflows/checks.yml`.

**Official current external documentation:**

- Docker Engine installation (Ubuntu): <https://docs.docker.com/engine/install/ubuntu/>
- Compose environment interpolation: <https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/>
- Docker daemon post-installation permissions: <https://docs.docker.com/engine/install/linux-postinstall/>
- Official Caddy installation: <https://caddyserver.com/docs/install>
- Automatic HTTPS: <https://caddyserver.com/docs/automatic-https>
- Caddy reverse proxy: <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy>

**Revision scope:** This manual describes **Public V93-RC1 only**. It deliberately excludes Extended features and does not replace the administrator manual. Update and recheck these commands whenever the Dockerfile, Compose configuration, SQLite schema, security settings, application routes or restore scripts change.
