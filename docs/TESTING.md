# Development and verification

Use the existing checkout for cloud tasks; each task is isolated. There is no need to create a Git worktree unless explicitly requested.

## Backend

From the repository root, install `backend/requirements-dev.txt` in `.venv`. Run:

```bash
.venv/bin/python -m pytest -q
```

Default tests use a disposable SQLite database. PostgreSQL concurrency tests are explicitly skipped there. For complete validation, create a disposable PostgreSQL database ending in `_test`, then run with `TEST_DATABASE_URL` set to its SQLAlchemy URL:

```bash
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/attendance_test .venv/bin/python -m pytest -q
```

Set credentials securely in your shell/environment rather than committing them or copying real credentials into commands/history. The example URL above is a placeholder. On Windows use `.venv\Scripts\python.exe` and set `$env:TEST_DATABASE_URL` securely.

Tests reset the selected test database, never the configured application database. PostgreSQL test URLs must end in `_test`. Covered behaviors include login/CSRF/role restrictions, device enrollment, expiration, revocation, signed identification, signature tampering, server time, four slots, duplicate/concurrent scan protection, retry receipts, voiding, audited corrections, field-duty separation, month locking, image/ID output, and PDF contents.

## Admin browser

Install Node.js, then:

```bash
npm ci
npx playwright install chromium
npm run test:web
```

The test runner starts/stops its own isolated API on port 8765 and resets a disposable SQLite database. `WEB_TEST_DATABASE_URL` can select a PostgreSQL database ending in `_test`. The test-only account is created only by `scripts/run-web-tests.py`; never run that script against a real database. No seed/demo users are installed by normal app startup.

If Chromium is already installed, set `CHROMIUM_PATH` to its executable. The browser suite exercises employee creation, field duty, attendance correction/voiding, PDF retrieval, enrollment codes, operator account creation, audit history, logout, invalid login and mobile layout. Screenshots are written to ignored `test-results/`.

## Android

In `scanner/` with Flutter 3.47.6:

```bash
flutter pub get --enforce-lockfile
flutter analyze
flutter test
flutter build apk --debug
```

Tests cover endpoint validation, signature intent, operator authentication, native-signing integration through a mock channel, durable retry packets, server errors, Philippine time conversion, and login form validation. They do not substitute for physical camera / Android Keystore testing. Use the device acceptance checklist.

## Database backups

Install PostgreSQL 17 client tools. Run `scripts/database-backup.py backup`, create a separate empty restore database, then run its `restore` command. Verify actual row counts after restoration; archive listing alone does not prove recoverability.

## Cloud caches

In restricted cloud workspaces, keep caches under `/workspace`: `PUB_CACHE`, `GRADLE_USER_HOME`, `ANDROID_HOME`, `ANDROID_USER_HOME`, `ANALYZER_STATE_LOCATION_OVERRIDE`, `XDG_CONFIG_HOME`, and npm's `--cache`. Do not redirect HOME. Java/Gradle must use the supplied HTTP(S) proxy via supported `systemProp.http.proxyHost`/`systemProp.https.proxyHost` and corresponding port properties. Preserve TLS/checksum verification. The official Gradle distribution checksum is pinned in the wrapper configuration.

Flutter SDK/artifacts also require `storage.googleapis.com`, in addition to the existing package-manager network preset. Installation packages remain on disk; running API/database services must be restarted as needed. Never use real employee records in automated tests.

For standalone Dart CLI commands in a read-only home directory, use the supported `DASH__SUPPRESS_ANALYTICS=true` setting, alongside the analyzer state override, so analytics initialization does not try to create files under HOME.
