# Office acceptance before using real attendance

- [ ] Install on the actual Windows computer, initialize a new PostgreSQL database, and verify restart preserves records.
- [ ] Keep the server clock synchronized and use the same stable HTTPS hostname on the browser and phone.
- [ ] Confirm untrusted phones, revoked phones, disabled operators, and replaced IDs cannot submit scans.
- [ ] Test printed IDs on the actual phone under office lighting, including glossy ID covers and camera-permission denial/recovery.
- [ ] Verify employee photo/name before saving; canceling must not create attendance.
- [ ] Record all four actions. Confirm duplicates do not replace times and switching actions requires confirmation.
- [ ] Disconnect Wi-Fi during a save, restart the scanner, and retry the same pending request. Confirm there is only one record.
- [ ] Test Philippine-midnight date grouping, and correct the phone clock if request validation rejects it.
- [ ] Verify operator accounts cannot open the dashboard or edit attendance.
- [ ] Record full-day and half-day field duty; verify no arrival/departure times are created.
- [ ] Correct and void an entry; inspect original times, actor, reason, and change history. Test stale-edit rejection.
- [ ] Review a completed month, finalize it, verify edits are blocked, and reopen with a reason.
- [ ] Compare printed Form 48 against your office's accepted form. Check A4 margins, employee names, hours, blank undertime fields, certification, signatures and February/leap-year rows.
- [ ] Confirm field-duty notation/attachments with the approving office. The application supplies a separate summary, not automatic paid-time credit.
- [ ] Restore a backup into a separate database and inspect employee, attendance, device and audit records.
- [ ] Establish backup retention, access, working days, leave/holiday treatment, and the manual outage procedure. These office policies are not inferred by the app.

The application does not calculate lateness, absence, overtime, payroll or undertime. It does not issue digital signatures/certification or track employee location. Employees do not need personal devices/accounts in this version.
