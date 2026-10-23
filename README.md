# AICTE Flow — account-based local portal

Open http://127.0.0.1:4190 while the service is running. Do not open public/index.html directly.

## Start and sign in

Double-click Start-Portal.cmd, or run `python server.py` with Python 3.10 or newer. No packages are required. Leave the service running while using the portal.

All local demo passwords match their usernames. Use the quick portal login buttons to enter any workspace, or sign in manually. The account list is also saved in **data/LOCAL-ACCOUNTS.md**. Quick login uses the same authenticated API and role restrictions as manual login.

Institution accounts: **sunrise**, **coastal**. Staff accounts: **bureau**, **scrutiny**, **evc-coordinator**, **evc-expert**, **hearing**, **appeal**, **complaints**, **compliance**, **decision**, **rule-author**, **rule-publisher**, **admin**, **auditor**.

Each account opens its permitted dashboard. Sign out to change workspaces. Tabs in the same browser share a login; use separate browser profiles for simultaneous accounts.

## Workspace separation

| Workspace | Access |
| --- | --- |
| Institution | Own applications, approval conditions, certificates and leases, deadlines and activity |
| Scrutiny | Applications awaiting scrutiny and document verification |
| EVC coordinator / expert | Relevant visit queue, scheduling or visit review actions |
| SHC / SAC | Hearing or appeal queue |
| Complaint scrutiny | Complaints workspace |
| Compliance verifier | Compliance evidence and verification |
| Decision authority | Decision queue and issued decisions |
| Bureau / auditor | Oversight and reports, with role-specific write permissions |
| Rule author / publisher / administrator | Permitted configuration and activity; no institution case queue |

The API filters records for the signed-in account, validates permitted edits, and restricts uploaded evidence downloads to accessible applications. Institution names are fixed by the account. Role switching is no longer a dashboard control.

## Working flows

Create and submit a draft as an institution. Sign in as scrutiny to verify its documents and route it onward. Use EVC accounts for scheduling and visit review, the decision account for decisions, and the institution and compliance accounts for evidence submission and verification.

Changes persist in SQLite, with save feedback, revision conflict checks and periodic refresh. Activity is attributed to the authenticated account. Evidence uploads accept PDF, PNG, JPG and DOCX up to 5 MB.

Passwords use salted PBKDF2 hashes; sessions expire after eight hours. Failed sign-in attempts are throttled. Pending browser drafts are separated by username.

## Data and deployment

Stop the service before copying data/portal.sqlite3 for a simple backup, or use SQLite's backup API. Restarting preserves records. The source ZIP excludes the running database and passwords; a fresh installation creates its own accounts and sample records.

This is a local prototype on HTTP loopback with sample identities. Production use requires TLS, an approved identity and account lifecycle, institution membership management, reviewed committee assignments and rules, evidence scanning, security review and tested backups. Notifications remain simulated. This prototype does not claim official AICTE compliance.
