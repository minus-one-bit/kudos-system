# Kudos — internal peer recognition

Kudos is a small, self-contained web application that lets colleagues recognise each
other with a short public message, and gives administrators a moderation view to hide
or remove content that breaks the community guidelines.

It was built for the Datacom **spec-driven development** task. The requirements and
technical design live in [`SPECIFICATION.md`](SPECIFICATION.md); this README explains
how to run, test, and deploy the implementation.

---

## Features

- **Authentication & authorization** — username/password sign-in, server-side
  sessions, HttpOnly cookies, `employee` and `admin` roles.
- **Give kudos** — pick an active colleague and write up to 500 characters.
- **Recent kudos feed** — newest first, with pagination ("Load more").
- **Moderation** — administrators can hide, unhide, or soft-delete kudos and must
  record a reason. Every action is written to an audit trail.
- **Abuse controls** — duplicate detection, per-sender hourly limits, per-recipient
  hourly limits, URL-flood detection, optional word blocklist.
- **Validation everywhere** — empty messages, over-length messages, self-kudos,
  unknown recipients, and invalid CSRF tokens all return a consistent JSON error.
- **Responsive UI** — server-rendered Jinja2 pages, progressive enhancement with
  vanilla JavaScript, keyboard-friendly controls, and a dark-mode colour scheme.
- **Security headers** — CSP, `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, request IDs, and no-store caching for authenticated pages.
- **Test suite included** — pytest coverage of auth, CSRF, feed, validation, rate
  limits, pagination, XSS escaping, moderation, and the audit trail.

---

## Quick start

Requires Python 3.11+.

```powershell
cd kudos-system
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m scripts.seed
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

On macOS/Linux the activation command is `source .venv/bin/activate`.

### Demo accounts

| Username | Password    | Role     |
| -------- | ----------- | -------- |
| `admin`  | `admin123!` | admin    |
| `alice`  | `alice123!` | employee |
| `bob`    | `bob123!`   | employee |
| `carol`  | `carol123!` | employee |
| `dave`   | `dave123!`  | employee |

The seed script is idempotent: run it again at any time and existing demo data is
left untouched.

---

## Tests

```powershell
pytest
```

The suite uses FastAPI's `TestClient` and a temporary SQLite database per test, so it
never touches `kudos.db` and can run in a clean checkout. The same suite runs in CI
via `.github/workflows/tests.yml`.

Useful subsets:

```powershell
pytest tests/test_auth.py -v
pytest tests/test_kudos.py -v
pytest tests/test_moderation.py -v
```

---

## API

All JSON endpoints require a signed-in session. Mutating endpoints also require the
`X-CSRF-Token` header, whose value is returned by `GET /api/me` and embedded in the
pages as `<meta name="csrf-token">`.

| Method | Path                            | Auth  | Description                              |
| ------ | ------------------------------- | ----- | ---------------------------------------- |
| POST   | `/login`                        | —     | Form sign-in; `303` on success, `401` on failure |
| POST   | `/logout`                       | user  | Form sign-out with `csrf_token`          |
| POST   | `/kudos`                        | user  | No-JavaScript composer fallback          |
| GET    | `/api/me`                       | user  | Current user + CSRF token                |
| GET    | `/api/users?q=`                 | user  | Active colleagues, excluding the caller  |
| GET    | `/api/kudos?limit=&offset=`     | user  | Visible kudos, newest first              |
| POST   | `/api/kudos`                    | user  | Create a kudos (`201`)                   |
| GET    | `/api/admin/kudos`              | admin | All kudos, including hidden/deleted      |
| POST   | `/api/admin/kudos/{id}/hide`    | admin | Hide a kudos (reason required)           |
| POST   | `/api/admin/kudos/{id}/unhide`  | admin | Restore visibility                       |
| DELETE | `/api/admin/kudos/{id}`         | admin | Soft-delete (reason required)            |
| GET    | `/healthz`                      | —     | Liveness probe                           |

Errors always use the same envelope:

```json
{ "error": { "code": "RATE_LIMITED", "message": "…" } }
```

Notable status codes: `401` unauthenticated, `403` forbidden / bad CSRF, `404` not
found, `409` duplicate kudos, `422` validation failure, `429` rate limited (with a
`Retry-After` header).

---

## Project layout

```
kudos-system/
├── SPECIFICATION.md           # requirements + technical design (source of truth)
├── README.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── app/
│   ├── main.py                # app factory, middleware, error handlers
│   ├── config.py              # environment-driven settings
│   ├── db.py                  # schema, connections, WAL
│   ├── security.py            # PBKDF2 hashing, tokens
│   ├── services.py            # domain logic (kudos, sessions, moderation)
│   ├── dependencies.py        # auth / admin / CSRF dependencies
│   ├── schemas.py             # request models
│   ├── timeutil.py            # UTC ISO helpers
│   ├── templating.py
│   ├── routers/               # auth, pages, JSON API, moderation API
│   ├── templates/             # Jinja2 pages and partials
│   └── static/                # CSS + progressive-enhancement JS
├── scripts/
│   └── seed.py                # idempotent demo data
└── tests/                     # pytest suite
```

---

## Configuration

Settings are environment variables read at startup (see `app/config.py`):

| Variable                   | Default          | Purpose                                      |
| -------------------------- | ---------------- | -------------------------------------------- |
| `KUDOS_DB`                 | `kudos.db`       | SQLite database path                          |
| `KUDOS_SESSION_COOKIE`     | `kudos_session`  | Session cookie name                           |
| `KUDOS_SESSION_TTL_HOURS`  | `8`              | Server-side session lifetime                  |
| `KUDOS_SECURE_COOKIES`     | `0`              | Set to `1` when serving over HTTPS            |
| `KUDOS_BLOCKLIST`          | *(empty)*        | Comma-separated prohibited terms              |

Run with `KUDOS_SECURE_COOKIES=1` in production; cookies are `HttpOnly` and
`SameSite=Lax` in all environments.

---

## Design decisions

- **Server-rendered pages, not an SPA.** The feed and composer work without
  JavaScript: the composer falls back to a normal form POST to `/kudos` with a hidden
  CSRF field and a Post/Redirect/Get cycle. The JS layer only adds async submission,
  pagination, and moderation buttons. This keeps the critical path accessible and easy
  to test.
- **SQLite with WAL.** A single writer with WAL is a good fit for an internal tool at
  this scale. All connections set `foreign_keys = ON`; one connection is opened and
  closed per request.
- **Soft delete plus audit.** Deleting a kudos never removes the row, so moderation
  is reversible and accountable. `is_visible`, `is_deleted`, `moderated_by`,
  `moderated_at`, and `reason_for_moderation` are stored on the kudos itself, with a
  separate `moderation_audit` table recording every action.
- **Server-side sessions.** Only an opaque 256-bit token is stored in the cookie.
  Session records can be revoked immediately and are deleted lazily when expired.
- **Two CSRF paths.** JSON calls send `X-CSRF-Token`; the sign-out form sends a hidden
  `csrf_token` field.
- **Defence in depth.** Parameterised SQL everywhere, output escaping in Jinja,
  `textContent` in JavaScript, PBKDF2-HMAC-SHA256 with 260,000 iterations, a CSP that
  forbids inline scripts, and consistent validation both client-side and server-side.
- **Explicit error vocabulary.** Stable machine-readable error codes make the API
  predictable for tests and future clients.

---

## Docker

```powershell
docker compose up --build
```

The compose file seeds the demo data on start and persists the database in the
`kudos-data` volume. The service listens on <http://127.0.0.1:8000>.

For a real deployment, terminate TLS in front of the app, set
`KUDOS_SECURE_COOKIES=1`, and remove or replace the demo seed step.

---

## Known limitations / next steps

- Demo credentials are seeded for convenience. A production version would integrate
  with the company identity provider (SSO/OIDC) instead of local passwords.
- Rate limiting and duplicate detection read from SQLite; a multi-instance deployment
  should move these counters to a shared store (for example Redis).
- SQLite is ideal for a single instance; PostgreSQL is the natural next step if the
  feed grows or multiple app instances are needed.
- Editing kudos, reactions, notifications, and recipient leaderboards were
  intentionally left out of v1 (see the open questions in `SPECIFICATION.md`).
