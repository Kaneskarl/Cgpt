# First-version validation

Validated in the Linux cloud workspace on 2026-10-08:

| Check | Result |
|---|---|
| Backend integration suite against PostgreSQL 17 | 20 passed, including concurrent scans/retries and timezone loading without an OS timezone database |
| Flutter client/unit/widget suite | 8 passed |
| Chromium admin workflow and mobile-layout suite | 2 passed |
| Flutter static analysis | Passed |
| Android debug APK, including native Kotlin/Keystore code compilation | Built successfully |
| PostgreSQL custom-format backup and actual restore into a separate database | Passed; counts matched across all 10 tables |
| Windows PowerShell script syntax | All 3 scripts parsed successfully |
| Form 48 | PDF content checked; A4 layout inspected |

The APK is `scanner/build/app/outputs/flutter-apk/app-debug.apk` in this workspace. Build outputs are ignored by Git; rebuilding is documented in WINDOWS_SETUP.md. Source files are prepared for review, not deployed to the office server.

Remaining acceptance work: installation/startup on the actual Windows server, physical Android camera/Keystore operation, office Wi-Fi/HTTPS, and printer/form approval. See ACCEPTANCE.md. Release signing requires an office-owned keystore; this is a debug test APK.

The pinned toolchain currently emits a Kotlin compatibility warning when building. The build succeeds with Flutter 3.47.6; coordinate future Flutter/AGP/Kotlin upgrades and migration to built-in Kotlin. The backend test runner emits an httpx deprecation warning, with all tests passing.

Cloud configuration draft: installation commands, agent startup instructions, and the `storage.googleapis.com` Flutter-download domain were saved. Saving does not publish the environment or verify restoration in a new task. Review and save the changes in environment settings, then publish to preserve the prepared environment.
