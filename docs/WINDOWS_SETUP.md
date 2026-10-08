# Windows test setup

Use Windows 10/11, Python **3.12** (with the `py` launcher), and PostgreSQL **17**. The Android phone needs Android **8.0+**, a camera, automatic date/time, and access to the same private network. The server needs internet to download tools/dependencies; daily attendance does not.

## 1. Prepare the database

Choose one option.

**Native PostgreSQL:** Install PostgreSQL 17 using its official Windows installer. In pgAdmin, create a login role `attendance` with a strong password, then create a database `attendance` owned by that role. Do not use the PostgreSQL superuser for the app. Add `C:\Program Files\PostgreSQL\17\bin` to PATH for backup tools.

**Docker PostgreSQL:** Install and start Docker Desktop, using Linux containers. The included `compose.yml` runs only PostgreSQL, persists its data, and binds port 5432 to localhost. Do not delete its volume to resolve an installation problem.

## 2. Install and create the first admin

Copy/clone this repository to a path such as `C:\Cgpt`. Open PowerShell there:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\Setup-Windows.ps1
# Or, if using Docker Desktop:
.\scripts\Setup-Windows.ps1 -Database Docker
```

The script creates `.venv`, installs pinned packages, creates `.env` if missing, restricts its file permissions, initializes the schema, and prompts for the first admin password. Native setup prompts for the database connection. It never prints passwords or replaces existing `.env`/accounts. Rerunning refreshes dependencies and preserves existing data. If setup is already configured, don't switch database modes without explicitly updating and checking `.env`.

If your machine's policy forbids script execution, follow your IT policy or run the equivalent commands manually. The execution-policy change above affects this PowerShell process only.

Manual initialization from the repository root:

```powershell
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'backend'); from app.cli import main; sys.argv=['app.cli','init']; main()"
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'backend'); from app.cli import main; sys.argv=['app.cli','create-admin']; main()"
```

For manual setup, copy `.env.example` to `.env`, set your percent-encoded database URL, and generate `JWT_SECRET` locally with Python's `secrets.token_urlsafe(48)`. Keep that file private. There is no default production admin password.

## 3. Start the admin dashboard

```powershell
.\scripts\Start-Windows.ps1
```

Open `http://127.0.0.1:8000` on that Windows computer. Log in, add employee profiles/photos, and create an **operator** account under Accounts. Use Print ID to generate each employee's PDF; print at actual size and test the QR before distributing IDs.

For temporary debug phone testing with disposable records:

```powershell
.\scripts\Start-Windows.ps1 -Lan
```

Find the computer's IPv4 address with `ipconfig`. Reserve it through the router's DHCP settings. Allow TCP port 8000 in Windows Firewall **only on the private profile and from the local subnet**. In elevated PowerShell, if your IT policy permits:

```powershell
New-NetFirewallRule -DisplayName 'Attendance debug API' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private -RemoteAddress LocalSubnet
```

The phone's debug server address is then `http://<WINDOWS_IPV4>:8000`. Guest Wi-Fi/client isolation can block the connection. HTTP is for controlled test data only; use HTTPS before entering real employee data.

## 4. Build/install the Android scanner

Install Flutter **3.47.6**, Android Studio, Android SDK platform **36**, build tools **36.0.0**, NDK **28.2.13676358**, and a compatible JDK (Android Studio's bundled JDK works). Run `flutter doctor` and complete the Android SDK license process on your machine.

```powershell
cd scanner
flutter pub get --enforce-lockfile
flutter analyze
flutter test
flutter build apk --debug
```

The test APK is `scanner\build\app\outputs\flutter-apk\app-debug.apk` relative to the repository root. Install it through Android Studio, `flutter run`, or `adb install -r <APK_PATH>`. Only enable USB debugging/app installation from your trusted development computer. The APK does not bundle a server; enter its address in the login screen.

Sign in with the operator account. In the admin website, open Scanner device and generate an enrollment code. Enter it on the phone within ten minutes. Enrollment is one-use; only one active phone is allowed. Grant camera access, select the action, scan an ID, verify the photo/name, then confirm.

## 5. HTTPS and release use

Give the server a stable internal DNS hostname, such as `attendance.office.internal`, resolving to its reserved address from both the phone and computer. Install Caddy from its official distribution, adapt `deploy/Caddyfile`, and run:

```powershell
caddy run --config deploy\Caddyfile
```

Keep the API bound to `127.0.0.1:8000`; expose Caddy's HTTPS port 443 only to the private local subnet. Trust Caddy's **local root certificate** on the admin computer and managed Android phone through their certificate-installation settings. On Windows it is normally under `%APPDATA%\Caddy\pki\authorities\local\root.crt`, depending on the account running Caddy. Export only the public certificate, never its private key. The phone must reach a certificate-matching hostname. This works without public internet or a purchased domain.

Set `COOKIE_SECURE=true` in `.env` and restart the API. Use the HTTPS address in the browser and scanner. Choose this stable address before enrolling the production phone; changing the enrolled server address requires admin revocation and resetting app data, followed by re-enrollment. Do not bypass certificate checks.

Create a release keystore outside the repository with `keytool` (passwords are prompted):

```powershell
keytool -genkeypair -v -keystore C:\AttendanceSecrets\scanner-release.jks -alias office-scanner -keyalg RSA -keysize 2048 -validity 10000
```

Create ignored `scanner\android\key.properties` locally:

```properties
storeFile=C:/AttendanceSecrets/scanner-release.jks
storePassword=YOUR_LOCAL_KEYSTORE_PASSWORD
keyAlias=office-scanner
keyPassword=YOUR_LOCAL_KEY_PASSWORD
```

Then run `flutter build apk --release`. Release builds refuse to use the debug signing key or an HTTP server address. A release APK cannot update a debug-signed install; revoke the test enrollment first, uninstall the debug app, then enroll the release app. Preserve the release signing key for future updates; do not commit it.

For a default PKCS12 keystore, use the same password for the key and the keystore.

Keep the Windows server awake during working hours and enable automatic Windows time synchronization. Configure API/Caddy startup under an appropriate Windows service account or Task Scheduler according to your IT policy. Processes must restart after a reboot; saved files do not keep them running.

## 6. Backups

From the root:

```powershell
.\scripts\Backup-Windows.ps1
```

The helper uses `pg_dump --format=custom`, validates the archive with `pg_restore --list`, and only marks the file complete after success. It retains all backups; establish retention/storage policy separately. Use Windows Task Scheduler to run this script daily under an account that can read `.env`. Copy backups to a second secured disk/location and restrict their permissions; they contain attendance data and password hashes. Protect `.env` and the release keystore separately.

Test restoration to a **new empty database** created in pgAdmin, owned by the same app role:

```powershell
.\.venv\Scripts\python.exe scripts\database-backup.py restore --archive backups\YOUR_BACKUP.dump --target-database attendance_restore_test
```

Restore refuses the live database and nonempty targets. It does not switch the running application to that database. Inspect restored counts/reports before deciding whether to recover production. Docker users still need PostgreSQL 17 client tools on Windows to use these helpers.
