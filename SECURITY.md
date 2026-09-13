# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in SpoolUp, please report it privately:

- **Email:** ozturkalihadi@gmail.com
- **Do NOT** open a public GitHub issue for security reports.

Please include a description of the vulnerability, steps to reproduce, and the potential impact. You can expect an acknowledgment within 72 hours.

## Credential Handling

SpoolUp deals with several sensitive credentials. Follow these rules:

| Credential | Where it lives | Rule |
|---|---|---|
| `client_secrets.json` | Your PC/Mac (auth machine) | Never commit; never copy to the printer unless required |
| `youtube_token.json` | Printer (`/usr/data/spoolup/`) | Never commit; treat as a password |
| `video_management/.env` | VMS server | Never commit; contains `SECRET_KEY` and TikTok/YouTube secrets |
| `video_management/data/` | VMS server | Contains SQLite DB, tokens, and session data — restrict filesystem permissions |
| Moonraker API key | `.env` (`MOONRAKER_API_KEY`) | Optional, but recommended on untrusted networks |

All of the above are covered by `.gitignore`. Verify before every commit:

```bash
git status --ignored | grep -E "client_secrets|youtube_token|\.env|data/"
```

## Video Management System (VMS) Security

The web application in `video_management/` ships with the following protections:

- **JWT authentication** — All `/api/*` endpoints require a bearer token (see `auth/security.py`, `auth/dependencies.py`)
- **Login rate limiting** — Failed login attempts are throttled (`MAX_LOGIN_ATTEMPTS` within a 15-minute window, see `auth/rate_limiter.py`)
- **Security headers** — `SecurityHeadersMiddleware` adds hardening headers to every response
- **Registration lockdown** — `ALLOW_REGISTRATION=false` by default; enable only temporarily for initial setup, or use `ADMIN_USERNAME`/`ADMIN_PASSWORD` to auto-create an admin on first start
- **Audit logging** — Sensitive actions are recorded in the `AuditLog` table
- **Token-in-query-param auth** — Supported only for `<video>`/`<img>` streaming endpoints (`/api/videos/{id}/stream`, `/api/videos/{id}/thumbnail`) where headers cannot be set; do not use query-param tokens elsewhere, and be aware they can appear in logs and browser history

### Deployment Recommendations

1. **Generate a strong `SECRET_KEY`** (at least 32 random bytes):
   ```bash
   openssl rand -base64 32
   ```
2. **Keep `DEBUG=false`** in production.
3. **Serve behind HTTPS** (reverse proxy or Tailscale) — JWTs and query-param tokens are bearer credentials.
4. **Restrict CORS origins** to your actual frontend origin(s).
5. **Back up `data/vms.db`** — it holds all upload history and analytics.

## Printer Runtime Security

- The printer-side daemon (`spoolup/`) loads a pre-generated OAuth token and never performs an OAuth flow on the printer.
- OAuth libraries are intentionally **not installed** on the printer to reduce attack surface and footprint.
- Do not expose Moonraker or the webcam stream to the public internet without authentication.

## Scope

The following are **out of scope** for vulnerability reports:

- Issues in third-party dependencies (report upstream; still feel free to notify us)
- Vulnerabilities requiring physical access to an already-unlocked printer
- Self-inflicted misconfigurations (e.g., committing your own secrets)

## Supported Versions

Security fixes are applied to the `main` branch. Older snapshots are not maintained.
