# Kudos System — Specification

| | |
|---|---|
| **Status** | Approved |
| **Version** | 1.0 |
| **Owner** | Graduate Developer, Datacom Internal Tools |
| **Last updated** | 2026-10-17 |
| **Scope** | Internal employee portal feature: peer-to-peer recognition |
| **Repository** | https://github.com/minus-one-bit/kudos-system |

---

## 1. Overview

### 1.1 Problem

Employees have no lightweight, visible way to recognise each other's work. The original request was:

> "We need a way for people to give kudos to each other."

### 1.2 Goal

Ship a small, secure internal feature that lets an authenticated employee:

1. choose a colleague from a list,
2. write a short message of appreciation,
3. submit it, and
4. see recently submitted kudos in a feed on the dashboard.

Administrators must be able to moderate inappropriate content.

### 1.3 Non-goals (v1)

- Anonymous kudos.
- Points, badges, rewards, or integration with HR systems.
- Email / Slack notifications.
- Rich text, images, or attachments.
- Mobile native apps.
- Editing kudos after submission.
- Per-department visibility rules.

### 1.4 Success metrics

| Metric | Target |
|---|---|
| Kudos submitted per week | ≥ 30% of active employees |
| p95 feed response (100k kudos) | < 300 ms |
| Moderation action latency | < 200 ms |
| Zero XSS / CSRF findings in review | Required |

---

## 2. Roles and permissions

| Role | Capabilities |
|---|---|
| **Employee** (default) | Sign in/out; list colleagues; submit kudos; read the feed; view own profile. Cannot moderate. |
| **Administrator** | Everything an employee can do, plus: view hidden/deleted kudos, hide/unhide, soft-delete, and record a moderation reason. |

Authorization is enforced server-side on every endpoint. Hiding UI controls is not a security control.

---

## 3. Functional Requirements

### 3.1 User stories

**US-01 — Authentication**
As an employee, I can sign in with my username and password so that only colleagues can access the Kudos feature.

**US-02 — Session management**
As an employee, I can sign out, and my session expires automatically after eight hours so that a shared machine cannot be misused.

**US-03 — Select a colleague**
As an employee, I can select another active employee from a searchable list so that I can direct kudos to the right person.

**US-04 — Write a message**
As an employee, I can write a message of appreciation of up to 500 characters, with a live character counter, so that I know what I am submitting.

**US-05 — Submit kudos**
As an employee, I can submit kudos and receive immediate confirmation so that I know it was stored.

**US-06 — Public feed**
As an employee, I can view a feed of the most recent visible kudos on the dashboard, paginated newest-first, so that recognition is visible across the team.

**US-07 — Administrator hide**
As an administrator, I can hide an inappropriate kudos message from the public feed, with a recorded reason, so that other employees no longer see it while the record is preserved for audit.

**US-08 — Administrator unhide**
As an administrator, I can restore a previously hidden kudos if I hid it in error.

**US-09 — Administrator delete**
As an administrator, I can soft-delete an inappropriate kudos, with a recorded reason, so that it is removed from every feed while the audit trail remains.

**US-10 — Moderation audit**
As an administrator, I can see who moderated a kudos, when, and why, so that moderation decisions are accountable.

**US-11 — Rate limiting and duplicate prevention**
As the system, I reject spam: duplicate submissions within 10 minutes, more than 20 kudos per user per hour, or more than 3 kudos to the same recipient per hour.

**US-12 — Responsive design**
As an employee, I can use the feature on a phone, tablet, or desktop so that recognition is not tied to a desk.

### 3.2 Acceptance criteria

#### US-01 Authentication
- [ ] `POST /login` with valid credentials creates a server-side session and sets an `HttpOnly`, `SameSite=Lax` cookie.
- [ ] Invalid credentials return `401` and a generic "Invalid username or password" message (no user enumeration).
- [ ] Passwords are stored as PBKDF2-HMAC-SHA256 hashes with a per-user salt and ≥ 260,000 iterations.
- [ ] Inactive users cannot sign in.

#### US-02 Session management
- [ ] Sessions expire 8 hours after creation.
- [ ] `POST /logout` deletes the server-side session and clears the cookie.
- [ ] A request with an expired or unknown cookie is treated as unauthenticated.

#### US-03 Select a colleague
- [ ] `GET /api/users` returns active employees other than the caller, max 200 results.
- [ ] Optional `q` parameter filters case-insensitively by display name or username.
- [ ] The dashboard renders the list in a `<select>` control for progressive enhancement.

#### US-04 Write a message
- [ ] The textarea enforces `maxlength="500"`.
- [ ] A counter shows `0 / 500` and updates as the user types.
- [ ] Leading and trailing whitespace is stripped before validation.

#### US-05 Submit kudos
- [ ] `POST /api/kudos` with a valid `recipient_id` and `message` returns `201` and the created record.
- [ ] The new kudos appears at the top of the caller's feed without a full page reload.
- [ ] Validation failures return a machine-readable error code and a human-readable message.
- [ ] A user cannot give kudos to themselves.
- [ ] A user cannot give kudos to an unknown or inactive user.

#### US-06 Public feed
- [ ] `GET /api/kudos` returns visible, non-deleted kudos, newest first.
- [ ] Default page size is 20; `limit` is capped at 50; `offset` is non-negative.
- [ ] The response includes `items`, `total`, `limit`, and `offset`.
- [ ] New kudos are ordered by `created_at DESC, id DESC` to break ties deterministically.

#### US-07/08/09 Moderation
- [ ] Only users with `role = 'admin'` can call moderation endpoints; others receive `403`.
- [ ] `POST /api/admin/kudos/{id}/hide` sets `is_visible = 0`, records `moderated_by`, `moderated_at`, and a required `reason_for_moderation`, and writes an audit row.
- [ ] `POST /api/admin/kudos/{id}/unhide` sets `is_visible = 1` and writes an audit row.
- [ ] `DELETE /api/admin/kudos/{id}` sets `is_deleted = 1` and `is_visible = 0` (soft delete), records the reason, and writes an audit row.
- [ ] Hidden or deleted kudos never appear in `GET /api/kudos` or the dashboard feed.
- [ ] A moderation reason is required (3–300 characters) for hide and delete.
- [ ] Moderation is idempotent for hide/unhide; deleting an already-deleted kudos returns `404`.

#### US-10 Audit
- [ ] Every moderation action inserts a row into `moderation_audit` with the kudos id, admin id, action, reason, and timestamp.
- [ ] The admin view shows moderator name, timestamp, and reason for each moderated item.

#### US-11 Abuse controls
- [ ] The same sender → recipient → identical message within 10 minutes returns `409 DUPLICATE_KUDOS`.
- [ ] A sender exceeding 20 kudos in a rolling hour receives `429 RATE_LIMITED` with `Retry-After`.
- [ ] A sender exceeding 3 kudos to one recipient in a rolling hour receives `429 RATE_LIMITED`.
- [ ] Messages containing more than two URLs are rejected as likely spam (`422 SPAM_SUSPECTED`).
- [ ] Messages matching the configurable blocklist are rejected (`422 PROHIBITED_LANGUAGE`).

#### US-12 Responsive design
- [ ] Layout works at 360 px, 768 px, and 1280 px widths.
- [ ] Interactive controls meet a 44 × 44 px minimum touch target.
- [ ] Colour contrast meets WCAG 2.1 AA for body text.
- [ ] All form controls have associated labels.

### 3.3 Edge cases considered

| Case | Behaviour |
|---|---|
| Empty or whitespace-only message | `422 VALIDATION_ERROR` |
| Message > 500 characters | `422 VALIDATION_ERROR` (server-side; client `maxlength` is convenience only) |
| Self-kudos | `422 SELF_KUDOS_NOT_ALLOWED` |
| Unknown / inactive recipient | `422 INVALID_RECIPIENT` |
| Duplicate submission (double-click, retry) | `409 DUPLICATE_KUDOS` |
| Rapid-fire spam | `429 RATE_LIMITED` with `Retry-After: 3600` |
| Message with `<script>` or HTML | Stored as text; escaped by Jinja and rendered with `textContent` in JS; never interpreted |
| Admin hides an already hidden kudos | `200`, idempotent, new audit row |
| Admin unhides a deleted kudos | `404` (deleted items are terminal in v1) |
| Two admins moderate concurrently | Last write wins; both audit rows preserved |
| Expired session mid-form submission | `401 UNAUTHENTICATED`; UI prompts re-login |
| Database unavailable | `500` with a generic message; details only in server logs |
| Unicode / emoji in message | Supported; length counted in Python characters |
| Very long colleague list | Capped at 200 with `q` filtering; UI select remains usable |

---

## 4. Technical Design

### 4.1 Architecture

```
┌──────────────────────────────┐
│ Browser                      │
│  Jinja-rendered pages        │
│  + /static/js/app.js (fetch) │
└──────────────┬───────────────┘
               │ HTTPS, session cookie, CSRF header
┌──────────────▼───────────────┐
│ FastAPI application          │
│  ├─ middleware: session,     │
│  │   security headers,       │
│  │   request logging         │
│  ├─ page routers             │
│  ├─ JSON API routers         │
│  └─ services (validation,    │
│      rate limits, moderation)│
└──────────────┬───────────────┘
               │ sqlite3 (WAL)
┌──────────────▼───────────────┐
│ SQLite database              │
│  users, kudos, sessions,     │
│  moderation_audit            │
└──────────────────────────────┘
```

**Key decisions**

- **Server-rendered pages + fetch enhancements** rather than a SPA: fewer moving parts, no build step, same-origin cookies are simple, and the feed still works without JavaScript.
- **SQLite** for v1: the feature is low-write (tens of kudos/day), single-region, and internal. The data-access layer is isolated so a move to PostgreSQL is a driver change, not a rewrite.
- **Server-side sessions** rather than JWTs: immediate revocation on logout, no token-in-localStorage XSS exposure.
- **Soft delete** rather than `DELETE`: moderation decisions must remain auditable.

### 4.2 Database schema

All timestamps are ISO-8601 UTC strings (`YYYY-MM-DDTHH:MM:SS+00:00`).

#### `users`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, AUTOINCREMENT | |
| `username` | TEXT | UNIQUE, NOT NULL | Login identifier |
| `display_name` | TEXT | NOT NULL | Shown in the UI |
| `email` | TEXT | UNIQUE, NOT NULL | Internal contact |
| `password_hash` | TEXT | NOT NULL | `pbkdf2_sha256$iterations$salt$hash` |
| `role` | TEXT | NOT NULL, CHECK IN ('employee','admin'), DEFAULT 'employee' | |
| `is_active` | INTEGER | NOT NULL, DEFAULT 1 | 0 = cannot sign in / be selected |
| `created_at` | TEXT | NOT NULL | |

Index: `UNIQUE(username)`, `UNIQUE(email)`, `idx_users_active(is_active, display_name)`.

#### `kudos`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, AUTOINCREMENT | |
| `sender_id` | INTEGER | NOT NULL, FK → users(id) | |
| `recipient_id` | INTEGER | NOT NULL, FK → users(id) | |
| `message` | TEXT | NOT NULL, CHECK(length(message) BETWEEN 1 AND 500) | Plain text |
| `is_visible` | INTEGER | NOT NULL, DEFAULT 1 | Moderation field: 0 = hidden from feed |
| `is_deleted` | INTEGER | NOT NULL, DEFAULT 0 | Soft delete |
| `moderated_by` | INTEGER | NULL, FK → users(id) | Admin who last acted |
| `moderated_at` | TEXT | NULL | |
| `reason_for_moderation` | TEXT | NULL, CHECK(length ≤ 300) | |
| `created_at` | TEXT | NOT NULL | |

Constraints: `CHECK(sender_id <> recipient_id)`.

Indexes:
- `idx_kudos_feed(is_deleted, is_visible, created_at DESC, id DESC)` — feed query.
- `idx_kudos_sender_time(sender_id, created_at)` — rate limits and duplicates.
- `idx_kudos_recipient_time(recipient_id, created_at)`.

#### `sessions`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `token` | TEXT | PK | 256-bit URL-safe random |
| `user_id` | INTEGER | NOT NULL, FK → users(id) ON DELETE CASCADE | |
| `csrf_token` | TEXT | NOT NULL | Per-session random token |
| `created_at` | TEXT | NOT NULL | |
| `expires_at` | TEXT | NOT NULL | |

Index: `idx_sessions_expires(expires_at)`.

#### `moderation_audit`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, AUTOINCREMENT | |
| `kudos_id` | INTEGER | NOT NULL, FK → kudos(id) | |
| `admin_id` | INTEGER | NOT NULL, FK → users(id) | |
| `action` | TEXT | NOT NULL, CHECK IN ('hide','unhide','delete') | |
| `reason` | TEXT | NULL | |
| `created_at` | TEXT | NOT NULL | |

Index: `idx_audit_kudos(kudos_id, created_at DESC)`.

#### Relationships

```
users 1 ──── * kudos (sender_id)
users 1 ──── * kudos (recipient_id)
users 1 ──── * sessions
users 1 ──── * moderation_audit (admin_id)
kudos 1 ──── * moderation_audit
```

### 4.3 API endpoints

All `/api/*` endpoints return JSON. Errors use:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Message must be 1–500 characters." } }
```

| Method | Path | Auth | Request | Success | Errors |
|---|---|---|---|---|---|
| GET | `/healthz` | none | — | `200 {"status":"ok"}` | — |
| GET | `/login` | none | — | `200` HTML | — |
| POST | `/login` | none | form `username`, `password` | `303 → /` + cookie | `401 INVALID_CREDENTIALS` |
| POST | `/logout` | session | form `csrf_token` | `303 → /login` | `403 INVALID_CSRF` |
| GET | `/` | session | — | `200` HTML dashboard | `303 → /login` |
| GET | `/admin` | admin | — | `200` HTML moderation view | `303 → /login`, `403` |
| GET | `/api/me` | session | — | `200 {user, csrf_token}` | `401 UNAUTHENTICATED` |
| POST | `/kudos` | session + CSRF | form `recipient_id`, `message`, `csrf_token` | `303 → /` | `403`, `422` (re-renders dashboard) |
| GET | `/api/users` | session | `?q=` | `200 {items:[...]}` | `401` |
| GET | `/api/kudos` | session | `?limit=20&offset=0` | `200 {items,total,limit,offset}` | `401`, `422` |
| POST | `/api/kudos` | session + CSRF | `{recipient_id, message}` | `201 {id, sender, recipient, message, created_at}` | `401`, `403`, `409`, `422`, `429` |
| GET | `/api/admin/kudos` | admin | `?limit=&offset=&include_deleted=` | `200 {items,total,...}` | `401`, `403` |
| POST | `/api/admin/kudos/{id}/hide` | admin + CSRF | `{reason}` | `200 {id,is_visible:false,...}` | `401`, `403`, `404`, `422` |
| POST | `/api/admin/kudos/{id}/unhide` | admin + CSRF | `{reason?}` | `200 {id,is_visible:true,...}` | `401`, `403`, `404` |
| DELETE | `/api/admin/kudos/{id}` | admin + CSRF | `{reason}` | `200 {id,is_deleted:true,...}` | `401`, `403`, `404`, `422` |

**Error codes**: `UNAUTHENTICATED` (401), `FORBIDDEN` (403), `INVALID_CSRF` (403), `NOT_FOUND` (404), `DUPLICATE_KUDOS` (409), `VALIDATION_ERROR` / `SELF_KUDOS_NOT_ALLOWED` / `INVALID_RECIPIENT` / `PROHIBITED_LANGUAGE` / `SPAM_SUSPECTED` (422), `RATE_LIMITED` (429), `INTERNAL_ERROR` (500).

**Example — create kudos**

```http
POST /api/kudos
Cookie: kudos_session=...
X-CSRF-Token: ...
Content-Type: application/json

{ "recipient_id": 4, "message": "Thanks for unblocking the release — you saved the sprint!" }
```

```json
HTTP/1.1 201 Created

{
  "id": 42,
  "sender": {"id": 3, "display_name": "Alice Nguyen"},
  "recipient": {"id": 4, "display_name": "Bob Patel"},
  "message": "Thanks for unblocking the release — you saved the sprint!",
  "created_at": "2026-10-17T05:12:33+00:00"
}
```

### 4.4 Frontend components

```
base.html
├── Top bar: brand, current user, admin link (role-gated), sign-out form
├── login.html
│   └── LoginForm (username, password, error banner)
├── dashboard.html
│   ├── KudosComposer
│   │   ├── RecipientSelect (populated from users)
│   │   ├── MessageTextarea + CharacterCounter (0/500)
│   │   └── SubmitButton + StatusRegion (aria-live)
│   └── KudosFeed
│       ├── KudosCard × N (sender → recipient, message, timestamp)
│       ├── EmptyState
│       └── LoadMoreButton (offset pagination)
└── admin.html
    ├── ModerationTable (status, message, participants, moderator metadata)
    └── ModerationActions (hide / unhide / delete, reason prompt)
```

**Interactions**

1. Page load: server renders the first feed page and the colleague list, so the feature is usable without JavaScript.
2. Compose: client validates non-empty and ≤ 500 characters, then `POST /api/kudos` with the CSRF header. If JavaScript is unavailable, the same form posts to `/kudos` with a hidden CSRF field and redirects back to the dashboard (Post/Redirect/Get).
3. Success: prepend a `KudosCard` built with `document.createElement` and `textContent` (never `innerHTML` with user data); reset the form; announce via `aria-live`.
4. Failure: show the server's message inline; keep the draft text so it is not lost.
5. Load more: `GET /api/kudos?offset=...`; append; hide the button when `offset ≥ total`.
6. Moderation: buttons call the admin endpoints; hide/delete require a reason; on success reload the table.

### 4.5 Security considerations

| Risk | Control |
|---|---|
| Password theft | PBKDF2-HMAC-SHA256, 260k iterations, 16-byte salt, constant-time comparison |
| Session theft | `HttpOnly`, `SameSite=Lax`, `Secure` when `KUDOS_SECURE_COOKIES=1`; 8-hour expiry; server-side revocation |
| CSRF | Per-session token required in `X-CSRF-Token` for JSON writes and in a hidden field for logout |
| XSS | Jinja autoescaping; JS uses `textContent`; CSP `default-src 'self'` with no inline scripts/styles |
| SQL injection | Parameterised queries only; no string interpolation into SQL |
| Broken access control | Role checks in dependencies on every admin route; server-side filtering of hidden/deleted rows |
| User enumeration | Generic login error; constant response shape |
| Brute force | Login attempts are not rate-limited in v1 (see §8); production should add per-IP throttling at the reverse proxy |
| Spam / abuse | Duplicate window, per-user and per-recipient hourly caps, URL flood heuristic |
| Clickjacking | `X-Frame-Options: DENY` + `frame-ancestors 'none'` |
| MIME sniffing | `X-Content-Type-Options: nosniff` |
| Sensitive data in logs | Logs contain method, path, status, duration, request id — never passwords, cookies, or message bodies |
| Dependency risk | Minimal dependency surface (FastAPI, Uvicorn, Jinja2, python-multipart) |

### 4.6 Performance considerations

| Concern | Design |
|---|---|
| Feed size | Offset pagination, 20 per page, capped at 50 |
| Query cost | Covering index `(is_deleted, is_visible, created_at DESC, id DESC)` |
| Counting | `COUNT(*)` on the same filtered predicate; acceptable at internal scale |
| Colleague list | Capped at 200, optional `q` filter, indexed on `(is_active, display_name)` |
| Repeated reads | Static assets served with long-lived cache headers; HTML is `no-store` because it carries a CSRF token |
| Write amplification | One insert per kudos; audit writes only on moderation |
| Concurrency | SQLite WAL mode; short transactions; one connection per request |
| Future scale | Repository functions are isolated; migrate to PostgreSQL and keyset pagination if the feed exceeds ~1M rows or writes exceed SQLite's comfortable range |

### 4.7 Error handling and logging

- Domain errors raise `ServiceError(code, message, status_code, headers)` and are rendered by a single exception handler into the standard error envelope.
- Pydantic validation errors are normalised to `422 VALIDATION_ERROR`; field-level details are not exposed to the client.
- Unexpected exceptions are logged with a stack trace and a request id; the client receives a generic `500 INTERNAL_ERROR`.
- Every request logs: timestamp, request id, method, path, status, duration.
- Moderation actions are additionally recorded in `moderation_audit`.

### 4.8 Accessibility and responsive design

- Semantic landmarks (`header`, `main`, `nav`), one `h1` per page.
- Every input has a `<label>`; async status messages are announced with `aria-live="polite"`.
- Status messages use `aria-live="polite"`.
- Visible focus rings; keyboard-operable controls.
- Breakpoints: single column below 720 px; two-column dashboard (composer + feed) above 960 px.
- Touch targets ≥ 44 px; body text ≥ 16 px.

---

## 5. Implementation Plan

### 5.1 Task breakdown and dependencies

| # | Task | Depends on | Deliverable |
|---|---|---|---|
| 1 | Project skeleton, config, dependency manifest | — | `requirements.txt`, `app/config.py` |
| 2 | Database schema, connection helpers, migrations-on-start | 1 | `app/db.py` |
| 3 | Password hashing, sessions, CSRF primitives | 1 | `app/security.py` |
| 4 | Session middleware, auth dependencies, error envelope | 2, 3 | `app/dependencies.py`, `app/main.py` |
| 5 | User/auth pages and endpoints | 4 | `routers/auth.py`, `login.html` |
| 6 | Kudos service: validation, duplicates, rate limits | 2, 3 | `app/services.py` |
| 7 | Feed and compose API + dashboard UI | 5, 6 | `routers/api.py`, `dashboard.html`, `app.js`, `styles.css` |
| 8 | Moderation service, admin API and UI, audit log | 6 | `routers/admin.py`, `admin.html` |
| 9 | Seed script and README | 2, 5 | `scripts/seed.py`, `README.md` |
| 10 | Automated tests (auth, kudos, moderation, security) | 5, 7, 8 | `tests/` |
| 11 | Container packaging and deployment notes | 7, 8 | `Dockerfile`, `docker-compose.yml` |
| 12 | Repository initialisation and public push | 10, 11 | Public Git repository |

### 5.2 Testing strategy

| Layer | Tool | Coverage |
|---|---|---|
| Unit / service | pytest | Validation, duplicates, rate limits, moderation transitions, audit rows |
| API integration | FastAPI `TestClient` | Auth, CSRF, status codes, feed filtering, pagination, role enforcement |
| Security regression | pytest | Unauthenticated access, non-admin moderation, XSS payload stored as text, hidden kudos excluded from feed |
| Manual | Browser | Responsive layout at 360/768/1280 px, keyboard navigation, character counter |

**Definition of done**: all tests pass; `python -m compileall app` is clean; a fresh database can be seeded and the app served; README commands work from a clean checkout.

### 5.3 Deployment considerations

- **Environment variables**: `KUDOS_DB`, `KUDOS_SECURE_COOKIES`, `KUDOS_BLOCKLIST`.
- **Process**: `uvicorn app.main:app --host 0.0.0.0 --port 8000` behind a TLS-terminating reverse proxy.
- **Container**: `Dockerfile` based on `python:3.13-slim`; mount a volume for the SQLite file.
- **Secrets**: demo seed credentials must be replaced before any shared deployment.
- **Backups**: SQLite file + WAL checkpoint; nightly copy off-host.
- **Observability**: ship request logs to the central log platform; alert on 5xx rate and on moderation volume anomalies.
- **HTTPS**: required in production; set `KUDOS_SECURE_COOKIES=1` so cookies carry the `Secure` flag.

---

## 6. Requirements Traceability

| Requirement | Implementation | Test |
|---|---|---|
| US-01 Authentication | `routers/auth.py`, `security.py` | `test_auth.py::test_login_success_and_me`, `test_login_wrong_password` |
| US-02 Sessions | `main.py` middleware, `auth.py` logout | `test_auth.py::test_logout_invalidates_the_session`, `test_expired_session_is_rejected` |
| US-03 Colleague list | `GET /api/users`, dashboard `<select>` | `test_kudos.py::test_users_excludes_the_caller` |
| US-04 Message input | `dashboard.html`, `app.js` counter | Manual + `test_message_over_500_characters_is_rejected` |
| US-05 Submit | `POST /api/kudos`, `POST /kudos` form fallback | `test_create_kudos_appears_in_the_feed`, `test_form_submission_works_without_javascript`, `test_self_kudos_is_rejected` |
| US-06 Feed | `GET /api/kudos`, `KudosFeed` | `test_feed_pagination`, `test_hidden_kudos_is_not_in_the_public_feed` |
| US-07/08/09 Moderation | `routers/admin.py`, `services.moderate_kudos` | `test_moderation.py` |
| US-10 Audit | `moderation_audit` table | `test_moderation_writes_an_audit_trail` |
| US-11 Abuse controls | `services.create_kudos` | `test_duplicate_kudos_is_rejected`, `test_rate_limit_per_user` |
| US-12 Responsive | `styles.css` | Manual viewport checks |

---

## 7. Specification Refinement Log (architect review)

The first AI-generated draft covered the happy path only. The architect reviewed it and made the following deliberate changes.

### 7.1 Requirements change — moderation

**Added**: US-07 (hide), US-08 (unhide), US-09 (delete), US-10 (audit), and the acceptance criteria in §3.2.

**Why**: peer-generated content is user-generated content. Without a moderation path, the first inappropriate post becomes an incident with no response tool. Hiding is separated from deleting because most moderation actions are reversible, and the audit requirement exists so decisions can be reviewed later.

**Edge cases added by this review**: spam bursts, duplicate submissions, prohibited language, link floods, and the distinction between hide and delete.

### 7.2 Design change — schema

**Added to `kudos`**: `is_visible` (BOOLEAN, default true), `moderated_by`, `moderated_at`, `reason_for_moderation`, and `is_deleted`.

**Why**: `is_visible` supports reversible hiding. `is_deleted` supports removal from all surfaces while preserving the row. The three moderation metadata fields make the action attributable and explainable without a join. The separate `moderation_audit` table keeps the full history when a kudos is moderated more than once.

**Consequence**: the feed query must filter on `is_deleted = 0 AND is_visible = 1`, and the index was designed for exactly that predicate.

### 7.3 Additional architect decisions

- Rejected anonymous kudos: they maximise abuse and remove accountability.
- Rejected hard delete as the default: it destroys the audit trail.
- Required a reason for hide/delete, because "why was this removed?" is the first question in any moderation dispute.
- Chose server-side sessions over JWTs so logout is immediate.
- Chose server-rendered pages over a SPA to keep the operational surface small for an internal tool.

---

## 8. Open questions / future work

1. **Login throttling**: add per-IP/per-username backoff at the reverse proxy or in-app before external exposure.
2. **Profanity detection**: the v1 blocklist is static and intentionally simple; evaluate a moderation service or ML classifier if volume grows.
3. **Notifications**: email or chat notification to the recipient is the most requested follow-up.
4. **Keyset pagination**: replace offset pagination if the feed grows beyond ~1M rows.
5. **PostgreSQL migration**: swap the repository layer when multi-instance deployment is required.
6. **HR integration**: map users from the corporate directory instead of the seed script.
