# Office Attendance

An attendance system for a small office: one authorized Android scanning phone, an operator, printed employee QR IDs, and a browser-based administrator dashboard.

The phone and dashboard connect to a FastAPI server backed by PostgreSQL. Daily operation works on the office network without internet. Flutter builds the Android scanner; the dashboard is served by the same backend with no separate Node server or CDN.

Implemented features:

- Admin and operator accounts; no default production passwords.
- Employee profiles, photos, printable QR IDs, ID replacement and deactivation.
- One-phone enrollment using a one-time code and Android Keystore signing.
- Identity confirmation before saving any scan; server timestamps in Philippine time.
- Morning In, Morning Out, Afternoon In, Afternoon Out; duplicates and replay-safe retries.
- Attendance corrections, voiding mistaken entries, and read-only audit history.
- Full-day / morning / afternoon field-duty approvals, separate from scan times.
- Individual monthly Civil Service Form 48 PDFs and supplementary field-duty summaries.
- Month finalization / audited reopening, office settings, and PostgreSQL backup / safe restore helpers.

The reference hours are **08:00–12:00 and 13:30–17:00**. There are no late labels, absence assumptions, penalties, grace periods, or automatic undertime calculations. Undertime fields remain blank.

Start with [Windows setup](docs/WINDOWS_SETUP.md). See [architecture and rules](docs/ARCHITECTURE.md), [testing](docs/TESTING.md), and [acceptance checklist](docs/ACCEPTANCE.md).

This is a first version for controlled testing. Confirm the Form 48 print layout and field-duty treatment with your office before official use. Physical camera scanning, Android Keystore behavior, Windows operation, and your printer require device-side acceptance testing.
