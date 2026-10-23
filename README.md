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

Changes persist in the configured database, with save feedback, revision conflict checks and periodic refresh. Activity is attributed to the authenticated account. Evidence uploads accept PDF, PNG, JPG and DOCX up to 3 MB to fit serverless request limits.

Passwords use salted PBKDF2 hashes; sessions expire after eight hours. Failed sign-in attempts are throttled. Pending browser drafts are separated by username.

## Deploy directly to Vercel

This repository now includes a Vercel Python Function for `/api/*`, static-site output from `public/`, and a PostgreSQL adapter. **A persistent PostgreSQL database is required for Vercel.** Do not rely on SQLite on Vercel: serverless function filesystems are not a durable shared database.

1. Create a PostgreSQL database with a provider such as Neon or Supabase. Copy its connection string (prefer the provider's pooled/serverless connection string when available).
2. In Vercel, open **Project → Settings → Environment Variables** and add `DATABASE_URL` with that connection string for Production and Preview as required. Keep the URL private; do not put it in any `NEXT_PUBLIC_` variable.
3. Ensure Vercel deploys the repository root (the folder containing `vercel.json`, `api/`, and `public/`). Push the changes and redeploy.
4. Open the deployed URL. The first API request creates the required tables and seeds the initial demonstration workspace and accounts. The sample passwords match usernames, for example `sunrise` / `sunrise`, `bureau` / `bureau`, or `admin` / `admin`.

For Supabase Transaction Pooler URLs (port `6543`), the PostgreSQL connection explicitly disables Psycopg's automatic prepared statements, requires TLS, and uses a 10-second connection timeout. If initialization still fails, open Vercel **Logs**, filter for `/api/login` or `/api/me`, and inspect the `AICTE Flow database initialization failed` traceback. Do not paste or publish your full `DATABASE_URL`; share only the exception message after removing any credentials or sensitive host details.

`vercel.json` rewrites `/api/login`, `/api/me`, `/api/state`, `/api/version`, `/api/logout`, and `/api/evidence` to `api/index.py`. The frontend remains same-origin, so no separate CORS configuration or backend URL is needed. The `DATABASE_URL` is also used for sessions and uploaded evidence, so these persist between function invocations.

### Important demo-security warning

This remains a **demonstration prototype**, not a production AICTE system. Demo accounts have publicly predictable passwords and all demo roles are exposed through the login UI. Anyone with the public URL can sign in and may change the shared sample data. Do not enter real institution records, personal information, or real evidence. Before any real use, replace demo-account bootstrap with an administrator-controlled account setup, enforce strong individual credentials, and carry out an independent security review. Notifications remain simulated; this prototype does not claim official AICTE compliance.

## Local development and backup

Local development still uses SQLite: run `python server.py` and open `http://127.0.0.1:4190`. If `DATABASE_URL` is set locally, the app uses PostgreSQL instead. To back up a local run, stop the service before copying `data/portal.sqlite3`, or use SQLite's backup API. The ZIP excludes the running local database; a fresh local installation creates its own accounts and sample records.
