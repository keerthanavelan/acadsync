# AcadSync

A working Next.js + FastAPI prototype that turns Gmail or Outlook academic notices into reviewed calendar events. Gmail + Google Calendar and Outlook + Microsoft Calendar are implemented. Teams and Moodle are explicitly marked **Coming soon**. Each provider account has its own isolated workspace; accounts are not merged by email address.

## Quick start with PostgreSQL

Prerequisites: Docker Desktop with Compose. From this directory:

```sh
cp .env.example .env
docker compose up --build
```

Open **http://localhost:3000** and choose **Try the demo**. No Microsoft credentials are needed for demo mode. The demo runs the actual backend extraction, database, editing, approval and rejection pipeline; it never contacts Google or Microsoft or writes to an external calendar. Sample dates are relative to the day the demo is created. Each browser gets its own demo account.

On PowerShell, use `Copy-Item .env.example .env` instead of `cp` if preferred. Do not commit `.env`.

## Local development without Docker

Prerequisites: Python 3.12+, Node.js 22+, and npm. PostgreSQL is recommended. SQLite is supported for local demos and tests only.

Terminal 1:

```sh
cd backend
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Terminal 2:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://localhost:3000**, not `127.0.0.1:3000`, so the configured Origin and OAuth redirect match. Without `backend/.env`, the backend uses local SQLite and demo mode. For local PostgreSQL, create the database and put `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/academicflow` in `backend/.env`. The Docker hostname `db` is only for Compose.

## Connect Gmail (recommended for the college demo)

Google registration is already supported in the code. No Microsoft registration, Docker, extra Google SDK, or LLM key is needed for Gmail.

1. In your personal Google Cloud project, enable **Gmail API** and **Google Calendar API**.
2. In Google Auth Platform, keep the audience **External**, publishing status **Testing**, and add your personal Gmail under **Test users**.
3. For your **Web application** OAuth client (for example, `AcadSync Web Client`), set:
   - Authorized JavaScript origin: `http://localhost:3000` (not used by the server OAuth flow, but safe to configure).
   - Authorized redirect URI: `http://localhost:3000/api/auth/google/callback` (must match exactly).
4. Configure these scopes under Data Access: `openid`, `email`, `profile`, `https://www.googleapis.com/auth/gmail.readonly`, and `https://www.googleapis.com/auth/calendar.events.owned`.
5. Open `backend/.env`. If it does not exist, copy `backend/.env.example` to `backend/.env`. Set only your own credential values:

   ```dotenv
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   GOOGLE_REDIRECT_URI=http://localhost:3000/api/auth/google/callback
   ```

   `CREDENTIAL_KEY` must contain a Fernet encryption key. If one was generated during setup, keep it. Otherwise generate one with the Python command in the Microsoft setup section below. Never put these secrets in frontend variables, screenshots, Git, or chat.
6. Restart the backend **from the backend directory**. On Windows, run `start.cmd`; it uses the fresh `.venv-acadsync` environment when available. In another terminal, run `npm run dev` from `frontend`.
7. Open **http://localhost:3000** in Chrome or Edge. Use an ordinary browser for Google sign-in; Google may reject embedded app browsers. Choose **Get started with Gmail** or **Connected sources → Connect Gmail**. Select your test account and allow both email and calendar permissions.
8. Send a test message to this Gmail inbox:

   ```text
   Subject: CS301 Assignment
   Body: Assignment due November 10, 2026 at 5:00 pm. Venue: Online submission.
   ```

   Choose a future date if this example is past. Click **Sync now**, open **Event review**, edit if needed, and approve. Verify the event in the account's primary Google Calendar.

**Expected Google testing behavior:** only listed test users can connect. Google can display an unverified-app notice for your development app. Testing refresh tokens expire after seven days for Gmail scopes; use Reconnect Gmail when required. Public distribution may require Google's restricted-scope verification. The client display name does not change URLs or credentials.

**Troubleshooting:** `redirect_uri_mismatch` means the callback differs from the Web client's redirect URI. Access denied can mean the account is missing from test users or declined a scope. An API permission error can mean an API is disabled; enable both APIs and reconnect. A local 503 setup message means the server cannot see the required environment variables; save `backend/.env` and restart. A broken old virtual environment can be replaced by creating `.venv-acadsync` with Python 3.12+ and installing `requirements.txt` there. `backend/start.cmd` uses this environment first.

Google adapter details:

- `google_auth.py`: authorization-code flow with PKCE, constant-time state validation, encrypted tokens, automatic refresh, strict scope checks and identity lookup through Google's authenticated userinfo endpoint.
- `google_routes.py`: one-use server-side login state and isolated Google account sessions. Browser responses never include access tokens, refresh tokens or secrets.
- `google.py`: bounded Gmail paging, MIME decoding (plain text preferred, attachments ignored), transient body processing, and Google Calendar creation/update. A deterministic remote event ID prevents duplicate calendar creation when a response or database commit is lost.
- Initial Gmail sync scans Inbox messages from the last 30 days, up to 50 messages per click. If more remain, the response asks you to sync again. A fixed scan window is preserved across pages. Later scans use the last completed watermark with a two-minute overlap; notice hashes suppress repeats. Gmail is user-triggered polling, not webhooks or background delivery.
- A manually moved/imported old email might be outside the incremental date window. Use Reset sync to rescan the last 30 days. Deleted emails are ignored; already-approved calendar events are never automatically deleted.
- Google Calendar shows AcadSync-approved events only. Existing unrelated calendar events are not imported. Approval writes to the connected account's **primary calendar**; all-day end dates are exclusive.
- Disconnect deletes AcadSync's stored credentials. To revoke Google's server-side grant too, remove AcadSync in [Google Account connections](https://myaccount.google.com/connections). Deleting AcadSync data leaves events already written in Google Calendar untouched.

References: [Google server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server), [Gmail message listing](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list), [Calendar event creation](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert).

## Enable real Outlook (optional)

1. In Microsoft Entra admin center, register a **Web** application. For universities, use your tenant or organizational accounts. To support personal Microsoft accounts, choose the corresponding account type and set `MICROSOFT_TENANT_ID=common`.
2. Add the exact Web redirect URI **http://localhost:3000/api/auth/callback**. This is a confidential backend client, not an SPA registration. Do not enable implicit grants.
3. Configure Microsoft Graph **delegated** permissions: `User.Read`, `Mail.Read`, `Calendars.ReadWrite`. MSAL adds the OpenID/offline scopes. No application permissions, email-send, or mailbox-write permission is requested.
4. Create a client secret. Store its **value**, not secret ID, only in the server environment. Enter `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` and `MICROSOFT_TENANT_ID` in `.env` (Docker) or `backend/.env` (local).
5. Generate a Fernet key using the backend Python environment:

   ```sh
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Set the result as `CREDENTIAL_KEY`. Keep it stable and private: losing or replacing it invalidates stored encrypted caches and requires reconnection.
6. Restart the backend. Choose **Connect Outlook**, sign in and consent. Some institutions require an administrator to grant consent; the application cannot bypass that policy.
7. Click **Sync now**, open **Event review**, correct any uncertain details, and approve. Approval saves to the user's default Outlook calendar. Return to Outlook to verify the event. A changed notice returns to pending review; approving it updates the existing Outlook event.

Reference: [MSAL authorization-code flow](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens), [Graph message delta](https://learn.microsoft.com/en-us/graph/api/message-delta), [Graph create event](https://learn.microsoft.com/en-us/graph/api/user-post-events).

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL; local fallback is SQLite |
| `FRONTEND_URL` | Exact allowed browser origin; defaults to `http://localhost:3000` |
| `REDIRECT_URI` | Registered Microsoft Web callback |
| `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` | Backend-only Microsoft app credentials |
| `MICROSOFT_TENANT_ID` | Tenant ID, `organizations`, or `common` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Backend-only Google Web client credentials |
| `GOOGLE_REDIRECT_URI` | Exact registered Google callback URI |
| `CREDENTIAL_KEY` | Fernet encryption key for MSAL caches and OAuth flow state |
| `COOKIE_SECURE` | Set `true` under HTTPS; local HTTP requires `false` |
| `DEFAULT_TIMEZONE` | IANA timezone used for new users, default `Asia/Kolkata` |
| `DEMO_ENABLED` | Set `false` on a non-demo public deployment |
| `API_INTERNAL_URL` | Frontend build-time server rewrite target; never a public token variable |

In production use HTTPS, a strong PostgreSQL password, private database/backend networking, `COOKIE_SECURE=true`, exact production origins and redirect URI, durable database backups and a secret manager. The Next.js rewrite keeps API traffic same-origin. The included Docker images run as non-root. The backend disables access logs to avoid logging OAuth callback codes. Do not enable proxy logging of callback query strings.

## Architecture

- `frontend/app/ui.tsx`: responsive landing, dashboard, review, calendar, sources and settings. Pages have real loading, empty and error states. Browser state contains no Microsoft credentials.
- `backend/app/auth.py`: confidential MSAL authorization-code flow, nonce/state validation through MSAL, encrypted server-side caches, silent refresh, opaque HttpOnly sessions. Only a SHA-256 digest of each session token is persisted. Login sessions expire after 10 minutes; signed-in sessions after 12 hours.
- `backend/app/graph.py`: Outlook adapter with bounded retries, paging, delta cursor handling, profile retrieval, and idempotent calendar creation using `transactionId`.
- `backend/app/extraction.py`: transient HTML-to-text conversion, academic category detection, English rule-based date/time/venue extraction and explicit uncertainty warnings.
- `backend/app/schemas.py`: common validated event schema, timezone-aware timestamps and ordered start/end times.
- `backend/app/pipeline.py`: notice hashing, normalized duplicate checks, change detection and review-state transitions.
- `backend/app/db.py`: SQLAlchemy models for accounts, server sessions, event suggestions and minimal relevant notice metadata.
- `backend/app/main.py`: account-scoped API orchestration, same-origin mutation protection, approval, settings, disconnect and data deletion.

Future email adapters should return the same normalized message shape (`id`, `subject`, `body.content`, `receivedDateTime`, optional `webLink`) and call `ingest`. A future LLM extractor can implement `extract()` and return validated `EventDetails` objects. No external LLM receives email content in this implementation.

## Behavior and intentional limits

- Initial sync reads the **Inbox only**, with a 30-day lookback. Delta sync processes at most ten pages of 50 messages per click and persists the continuation link, so large inboxes may need several syncs. Sync is user-triggered, not a background scheduler.
- Raw bodies are not persisted. Relevant subjects, received dates, content hashes and extracted event fields are stored. The Graph source URL links back to the original notice. Extracted descriptions are deliberately brief to avoid retaining unrelated email content.
- The English rule engine extracts **one suggestion per notice**. Multiple dates, unclear numeric dates, timezone abbreviations and changed deadlines are flagged. Numeric dates such as `05/11/2026` require manual input. Complex timetables, attachments and multilingual extraction are not implemented. Confidence is a rule score, not a calibrated statistical probability.
- Duplicate detection uses normalized title and start time. Deadline updates match the original message or an unambiguous normalized title; heavily reworded follow-up notices may require manual rejection of duplicates.
- Calendar views show AcadSync-approved events, not unrelated events already in Outlook. There is no two-way calendar import. Rejection of a proposed update leaves the previously saved Outlook event untouched.
- Disconnect removes stored tokens and sync cursor. Microsoft consent can also be revoked in Microsoft My Apps. Deletion removes AcadSync records and sessions, **not events already written to Outlook**.
- PostgreSQL row locks serialize sync and calendar approval. SQLite is for a single-process local demo only. Tables are created on first startup; future schema changes require a migration workflow before production use.
- Before a public multi-user release, add scheduled cleanup of expired OAuth/session rows and abandoned demo accounts, deployment-specific rate limiting, migrations, monitoring and operational retention policies.

## Verification

```sh
cd backend
python -m pytest -q
cd ../frontend
npm run build
```

Automated tests cover extraction, irrelevant mail, ambiguous/missing dates, repeated syncs, deadline changes, cross-account isolation, deletion, validation, failed calendar writes, idempotent approval and updating existing remote events. Google and Microsoft calls are mocked in integration tests. Google tests cover OAuth state/PKCE/replay, consent failures, encryption, refresh, MIME parsing, paging, synchronization, review, calendar retries, disconnection and deletion. The real demo workflow has also been exercised in a browser.

**Live Google/Microsoft OAuth and external calendar writes require your app credentials and consent and have not been verified against a real mailbox in this environment.** PostgreSQL deployment is supplied through Compose; this environment's runtime verification used SQLite because Docker/PostgreSQL were unavailable.
