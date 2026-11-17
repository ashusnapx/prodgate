# auth-sessions

Sign-in, sessions and account administration for a multi-organisation web app, with email and password only (no sign-up). Built with FastAPI and SQLAlchemy on SQLite.

## Accounts

- Each person belongs to one organisation and is an `admin` or a `member`. An organisation's first admin is created by the setup script (`users.bootstrap_admin`); everyone else is invited.
- Status: `invited` until their first sign-in, then `active`. A `disabled` account cannot sign in and all its sessions end. There is no re-enable.
- Passwords are at least 12 characters and may not contain the email's local part. Hashes are scrypt (`app/security.py`).

## Sign-in and sessions

- `POST /auth/sign-in {email, password}` returns a session token (shown once; only its SHA-256 is stored) and `must_set_password`. Each address gets five tries a minute; every attempt counts, successful or not, and the sixth within the minute gets `429`.
- Send the token as `Authorization: Bearer <token>`. A session lasts 12 hours from its last use (renewed at most every 15 minutes) or until it is revoked.
- `POST /auth/sign-out` ends the current session. `GET /me/sessions` lists your open sessions and `DELETE /me/sessions/{id}` ends one of them.

## One-time passwords

An invite or an admin reset gives the person a one-time password, which the admin hands over. While someone holds a one-time password, every route except `GET /me`, `POST /me/password` and sign-out refuses them with `403` until they choose their own password with `POST /me/password {new_password}`. Otherwise changing your password needs `current_password` too, and signs out your other sessions.

## Admin routes

All under `/admin`, for admins of the same organisation only:

| route | what it does |
|---|---|
| `GET /admin/users` | everyone in the organisation |
| `POST /admin/invites {email, display_name, role}` | create an invited account and a 7-day invite; returns the one-time password. The first sign-in with it, before the invite expires, accepts the invite. If an invite expires unused, invite the address again |
| `POST /admin/invites/{id}/revoke` | revoke a pending invite; it can no longer be used |
| `POST /admin/users/{id}/reset-password` | replace an active user's password with a one-time password and end every session opened with the old password |
| `POST /admin/users/{id}/disable` | disable an account and end its sessions |

Every admin action is written to `audit_events`. Errors come back as Problem Details JSON.

## Running

```
./run_tests.sh
```
