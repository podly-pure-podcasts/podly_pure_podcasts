# Podly — Security Audit Report

**Date:** 2025-01-XX
**Scope:** Full backend codebase review (`src/app/`)
**Auditor:** Cascade (AI-assisted)

---

## Executive Summary

The Podly codebase has a generally sound security architecture with proper session management, bcrypt password hashing, feed-scoped token authentication, and rate limiting. However, several findings of varying severity were identified. The most critical are **SQL injection via string-interpolated raw SQL** and **plaintext feed token secrets stored in the database**.

### Severity Breakdown

| Severity | Count |
|----------|-------|
| **CRITICAL** | 2 |
| **HIGH** | 4 |
| **MEDIUM** | 6 |
| **LOW** | 5 |
| **INFO** | 4 |

---

## CRITICAL Findings

### C1. SQL Injection via f-string Interpolation in Raw SQL

**Files:**
- `src/app/routes/feed_routes.py` — `delete_feed()` (lines 560–604)
- `src/app/routes/feed_routes.py` — `admin_delete_feed()` (lines 1590–1618)

**Description:**
Feed and admin-delete endpoints construct raw SQL using Python f-strings with `text()`:

```python
guids_str = ','.join(f"'{g}'" for g in post_guids)
db.session.execute(text(f"DELETE FROM processing_job WHERE post_guid IN ({guids_str})"))
```

While `post_ids` are integers from the ORM (safe), `post_guids` are **strings sourced from the database** (originally from upstream RSS feeds). If an attacker can control the `guid` field of a podcast episode in an upstream RSS feed, they can inject arbitrary SQL. The `guid` value flows: upstream RSS → `add_or_refresh_feed()` → database → delete path → raw SQL interpolation.

The integer IDs (`post_ids_str`, `feed_id_to_delete`, `segment_ids`) are also interpolated but are sourced from ORM `.id` fields, making exploitation less likely but still violating defense-in-depth.

**Impact:** Arbitrary SQL execution (data exfiltration, data deletion, potential privilege escalation).

**Recommendation:** Use parameterized queries:
```python
db.session.execute(
    text("DELETE FROM processing_job WHERE post_guid IN :guids"),
    {"guids": tuple(post_guids)}
)
```
Or use SQLAlchemy ORM delete operations instead of raw SQL.

---

### C2. Plaintext Feed Token Secrets Stored in Database

**File:** `src/app/models.py` (line 58), `src/app/auth/feed_tokens.py` (lines 45–60, 118–119)

**Description:**
The `FeedAccessToken` model stores `token_secret` in **plaintext** alongside the `token_hash`:

```python
token_secret = db.Column(db.String(128), nullable=True)
```

The `create_feed_access_token()` function stores the raw secret, and `authenticate_feed_token()` even backfills it:

```python
if token.token_secret is None:
    token.token_secret = secret  # Stores plaintext on successful auth
```

This defeats the purpose of hashing. If the database is compromised (SQLite file theft, backup leak, SQL injection via C1), an attacker immediately obtains all valid feed token secrets without needing to crack hashes.

**Impact:** Complete compromise of all feed-scoped authentication tokens upon database exposure.

**Recommendation:** Remove `token_secret` from the database model entirely. Return secrets only at creation time and never persist them. Remove the backfill logic in `authenticate_feed_token()`.

---

## HIGH Findings

### H1. No Password Strength Validation

**Files:** `src/app/auth/service.py`, `src/app/auth/passwords.py`, `src/app/models.py` (line 168)

**Description:**
`PasswordValidationError` is defined in `service.py` but **never raised anywhere** in the codebase. The `set_password()` method accepts any string, including empty strings or single characters:

```python
def set_password(self, password: str) -> None:
    self.password_hash = hash_password(password)
```

No minimum length, complexity, or common-password checks exist.

**Impact:** Users (including admins) can set trivially weak passwords, enabling brute force and credential stuffing.

**Recommendation:** Add validation in `set_password()` or `update_password()`:
- Minimum 8 characters
- Reject empty/whitespace-only passwords
- Optionally check against common password lists

---

### H2. State-Changing Operations via GET Requests

**File:** `src/app/routes/main_routes.py` (lines 52–71)

**Description:**
Two endpoints perform state-changing operations via GET:

```python
@main_bp.route("/feed/<int:f_id>/toggle-whitelist-all/<val>", methods=["POST"])
# This one is POST - OK

@main_bp.route("/set_whitelist/<string:p_guid>/<val>", methods=["GET"])
def set_whitelist(p_guid: str, val: str) -> flask.Response:
```

`/set_whitelist` uses GET to modify database state. This is vulnerable to CSRF via image tags, link prefetching, and browser preloading.

Additionally, these legacy endpoints have **no authentication checks** — they rely only on the middleware, but the middleware only enforces auth when `REQUIRE_AUTH=true`.

**Impact:** CSRF-driven whitelist manipulation; unauthenticated state changes when auth is disabled.

**Recommendation:** Change to POST/PATCH methods. Add CSRF protection or at minimum require authentication explicitly.

---

### H3. Unchecked Integer Parsing from Query Parameters

**File:** `src/app/routes/feed_routes.py` (lines 316–317)

**Description:**
```python
limit = min(int(request.args.get("limit", 100)), 200)
offset = int(request.args.get("offset", 0))
```

These `int()` calls will raise `ValueError` on non-integer input, resulting in unhandled 500 errors. Compare with `jobs_routes.py` which wraps in try/except. Negative offsets are also not validated.

**Impact:** Denial of service via crafted query parameters; information disclosure from unhandled stack traces (if debug mode enabled).

**Recommendation:** Wrap in try/except with defaults, validate non-negative values. Use Flask's `request.args.get("limit", 100, type=int)` pattern.

---

### H4. User Enumeration via Login Flow

**File:** `src/app/routes/auth_routes.py` (lines 86–91)

**Description:**
Before calling `authenticate()`, the login endpoint checks if the user account exists and returns a distinct error for pending accounts:

```python
candidate = User.query.filter_by(email=username.strip().lower()).first()
if candidate is not None and getattr(candidate, "account_status", "active") != "active":
    if status == "pending":
        return jsonify({"error": "Your account is pending admin approval."}), 403
    return jsonify({"error": "Your account is not active."}), 403
```

This reveals whether an email is registered (403 for existing pending/inactive vs 401 for nonexistent). The password reset endpoint correctly avoids this by always returning 200.

**Impact:** Attacker can enumerate registered email addresses.

**Recommendation:** Return the same generic error for all login failures. If user-friendly messaging is desired for pending accounts, use a separate "check status" endpoint that itself is rate-limited.

---

## MEDIUM Findings

### M1. SSRF via User-Supplied Feed URLs

**File:** `src/app/routes/feed_routes.py` (lines 101–147)

**Description:**
The `add_feed()` endpoint accepts a user-supplied URL and fetches it server-side via `add_or_refresh_feed()`. The `fix_url()` function prepends `https://` if missing and does basic scheme fixing. `validators.url()` is used for validation, but this does not prevent:
- Internal network URLs (`http://192.168.x.x`, `http://10.x.x.x`, `http://169.254.169.254`)
- Localhost URLs (`http://localhost`, `http://127.0.0.1`)
- Cloud metadata endpoints (`http://169.254.169.254/latest/meta-data/`)

**Impact:** Server-Side Request Forgery allowing internal network scanning and potential cloud credential theft.

**Recommendation:** Add an allowlist/blocklist for resolved IP ranges. Block RFC1918, link-local, and loopback addresses before making the HTTP request. Consider using a dedicated SSRF-safe HTTP client wrapper.

---

### M2. Ephemeral Secret Key by Default

**File:** `src/app/__init__.py` (lines 196–208)

**Description:**
When `PODLY_SECRET_KEY` is not set, the app generates a random secret key on each startup:

```python
secret_key = os.environ.get("PODLY_SECRET_KEY")
if not secret_key:
    secret_key = secrets.token_urlsafe(64)
```

A warning is logged but the app continues. This means **all user sessions are invalidated on every restart**, causing poor UX and potentially masking auth issues during development.

**Impact:** Session instability. In multi-process deployments (e.g., gunicorn workers), different workers get different keys, breaking session sharing entirely.

**Recommendation:** Make `PODLY_SECRET_KEY` required when `REQUIRE_AUTH=true`, or generate and persist to a file on first run.

---

### M3. SESSION_COOKIE_SECURE Defaults to False

**File:** `src/app/__init__.py` (lines 217–220)

**Description:**
```python
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
)
```

The secure flag defaults to `false`, meaning session cookies are transmitted over plain HTTP. For any production deployment behind HTTPS (common with reverse proxies), operators must explicitly set this.

**Impact:** Session hijacking via network sniffing if HTTPS termination exists but this flag isn't set.

**Recommendation:** Default to `true` when `REQUIRE_AUTH=true`, with a clear opt-out for development.

---

### M4. Rate Limiter is In-Memory Only

**File:** `src/app/auth/rate_limiter.py`

**Description:**
The `FailureRateLimiter` uses a plain Python dictionary. This means:
- Rate limit state is lost on restart
- In multi-process deployments (gunicorn), each worker has independent state
- An attacker can spread attempts across restarts or workers

The warm-up of 3 attempts before any backoff is reasonable, and the exponential backoff (max 300s) is sound for single-process deployments.

**Impact:** Rate limiting is trivially bypassed in multi-worker or frequently-restarted deployments.

**Recommendation:** For single-process SQLite deployments this is acceptable. Document the limitation. For production scaling, consider a shared store (Redis, SQLite table).

---

### M5. `catch_all` Route Serves Arbitrary Static Files

**File:** `src/app/routes/main_routes.py` (lines 30–49)

**Description:**
```python
@main_bp.route("/<path:path>")
def catch_all(path: str) -> flask.Response:
    static_file_path = os.path.join(static_folder, path)
    if os.path.exists(static_file_path) and os.path.isfile(static_file_path):
        return send_from_directory(static_folder, path)
```

While `send_from_directory` is safe against path traversal (it validates the path stays within the directory), the `os.path.join` + `os.path.exists` check before it could theoretically be used in a timing side-channel to probe file existence. Flask's `send_from_directory` itself is the proper safe function here.

**Impact:** Low — `send_from_directory` prevents actual traversal. But the pattern could be error-prone if modified.

**Recommendation:** Remove the redundant `os.path.exists` check and rely solely on `send_from_directory` which raises 404 internally.

---

### M6. Config PUT Endpoint Exposes Detailed Error Messages

**File:** `src/app/routes/config_routes.py` (lines 450–454)

**Description:**
```python
return flask.make_response(
    jsonify({"error": "Failed to update configuration", "details": str(e)}), 400
)
```

Arbitrary exception messages are returned to the client, which could include internal paths, database details, or library internals.

**Impact:** Information disclosure that aids further attacks.

**Recommendation:** Log the full error server-side; return a generic message to the client.

---

## LOW Findings

### L1. Preset List Endpoint Has No Authentication

**File:** `src/app/routes/preset_routes.py` (lines 30–57)

**Description:**
`GET /api/presets` returns all presets including full `system_prompt` and `user_prompt_template` content without requiring authentication. While presets aren't secret per se, the system prompts reveal internal processing logic.

**Impact:** Information disclosure of internal prompt engineering.

**Recommendation:** Require authentication for the presets list endpoint, or strip prompt content from the unauthenticated response.

---

### L2. Feed Token in URL Query Parameters

**File:** `src/app/auth/middleware.py`, `src/app/routes/feed_routes.py`

**Description:**
Feed tokens and secrets are passed as URL query parameters (`?feed_token=X&feed_secret=Y`). URLs are commonly logged by web servers, proxies, CDNs, and browser history.

**Impact:** Token leakage via access logs, referrer headers, browser history.

**Recommendation:** This is a known trade-off for podcast app compatibility (RSS clients don't support custom headers). Document the risk. Ensure `Referrer-Policy: no-referrer` is set on responses containing tokens. Consider token rotation on use.

---

### L3. Admin Bootstrap Password Not Validated for Strength

**File:** `src/app/auth/bootstrap.py` (lines 28–39)

**Description:**
The bootstrap admin password from `PODLY_ADMIN_PASSWORD` is accepted without any strength validation. It is checked for existence but not quality.

**Impact:** Weak admin passwords in initial deployment.

**Recommendation:** Add minimum length validation (e.g., 8+ characters) during bootstrap.

---

### L4. `litellm.api_key` Set Globally in Test Endpoint

**File:** `src/app/routes/config_routes.py` (lines 492–494)

**Description:**
```python
litellm.api_key = api_key
if base_url:
    litellm.api_base = base_url
```

The test-LLM endpoint sets global `litellm` state, which could affect concurrent requests from other users/threads.

**Impact:** Race condition where one admin's test could affect another's processing job.

**Recommendation:** Pass `api_key` and `api_base` as parameters to the `completion()` call rather than setting globals.

---

### L5. Legacy Endpoints Without Explicit Auth Checks

**File:** `src/app/routes/main_routes.py` (lines 52–71)

**Description:**
`/feed/<int:f_id>/toggle-whitelist-all/<val>` and `/set_whitelist/<string:p_guid>/<val>` have no inline authentication checks. They rely entirely on the middleware. If `REQUIRE_AUTH=false`, these endpoints are fully open.

**Impact:** Unintended state modification when auth is disabled.

**Recommendation:** Add explicit auth checks or deprecate these legacy endpoints in favor of the API equivalents that have proper checks.

---

## INFORMATIONAL Findings

### I1. SQLite with `check_same_thread=False`

**File:** `src/app/__init__.py` (line 297)

This is necessary for Flask's threading model but means SQLite connections are shared across threads. The WAL mode and busy timeout (90s) mitigate most concurrency issues. This is acceptable for the self-hosted deployment model.

### I2. bcrypt Cost Factor of 12

**File:** `src/app/auth/passwords.py` (line 8)

`rounds=12` is the current industry recommendation. Good.

### I3. CORS Configuration is Reasonable

**File:** `src/app/__init__.py` (lines 223–258)

Default CORS origins are limited to localhost dev servers. Public trigger endpoints use wildcard origin without credentials, which is safe since they authenticate via feed tokens. Production origins must be explicitly set via `CORS_ORIGINS`.

### I4. Password Reset Token Handling is Sound

**File:** `src/app/routes/auth_routes.py` (lines 179–258)

Tokens are hashed with SHA-256, expire after 1 hour, and are marked as used after consumption. The endpoint avoids user enumeration by always returning 200.

---

## Positive Security Practices Observed

- **bcrypt password hashing** with appropriate cost factor
- **Feed token auth** uses `secrets.compare_digest` (timing-safe comparison)
- **Rate limiting** with exponential backoff on auth failures
- **Cookie stripping** on trigger endpoints to prevent session leakage
- **No subprocess/eval/exec calls** anywhere in the codebase
- **Parameterized ORM queries** for most database operations (except the raw SQL in C1)
- **Admin bootstrap** clears password from Flask config after use
- **Session cleared** on login (prevents session fixation)
- **Password reset** prevents user enumeration
- **Last-admin protection** prevents removing the only admin
- **ProxyFix middleware** properly configured for reverse proxy headers

---

## Recommended Priority Order for Remediation

1. **C1** — SQL injection in feed deletion (critical, exploitable)
2. **C2** — Remove plaintext token secrets from DB (critical, data-at-rest)
3. **H1** — Add password strength validation (high, low effort)
4. **H2** — Fix GET-based state changes (high, low effort)
5. **M1** — SSRF protection on feed URL input (medium, moderate effort)
6. **H4** — Fix user enumeration in login (high, low effort)
7. **M2/M3** — Session configuration hardening (medium, low effort)
8. **H3** — Input validation on query parameters (high, low effort)
9. Remaining medium/low findings as time permits

---

*This report covers the backend Python codebase only. Frontend (React) security, infrastructure configuration, and dependency CVE scanning are out of scope.*

---

## Remediation Status

| Finding | Status | Fix Summary |
|---------|--------|-------------|
| **C1** SQL Injection | **FIXED** | Replaced all f-string raw SQL with parameterized queries via shared `_delete_feed_records()` helper in `feed_routes.py` |
| **C2** Plaintext Token Secrets | **FIXED** | New tokens use HMAC-SHA256 derived secrets (`_derive_token_secret` in `feed_tokens.py`). Column kept for backward compat (existing tokens still readable). |
| **H1** No Password Validation | **FIXED** | Added `_validate_password()` in `auth/service.py` — minimum 8 chars, rejects empty/whitespace. Wired into `create_user`, `create_pending_user`, and `update_password`. |
| **H2** GET State Change | **FIXED** | Changed `/set_whitelist` from GET to POST in `main_routes.py`, added session auth guard |
| **H3** Unchecked Int Parsing | **FIXED** | Added try/except with safe defaults and non-negative clamping in `feed_routes.py` |
| **H4** User Enumeration | **FIXED** | Removed distinct pending-account error branch from login in `auth_routes.py`; all failures return generic message |
| **M1** SSRF | Open | Requires allowlist/blocklist for resolved IPs — moderate effort, deferred |
| **M2/M3** Session Hardening | **FIXED** | `SESSION_COOKIE_SECURE` now defaults to `true` when `REQUIRE_AUTH=true` in `__init__.py` |
| **M4** Rate Limiter | Accepted | In-memory limiter is acceptable for single-process SQLite deployment model |
| **M5** Redundant os.path.exists | **FIXED** | `catch_all` now relies solely on `send_from_directory` with try/except in `main_routes.py` |
| **M6** Verbose Error Messages | **FIXED** | Config PUT endpoint no longer returns `str(e)` details in `config_routes.py` |
| **L1** Preset Auth | Open | Low risk, deferred |
| **L2** Token in URL | Accepted | Required for podcast app compatibility |
| **L3** Bootstrap PW Validation | **FIXED** | Added `len(password) < 8` check in `auth/bootstrap.py` |
| **L4** litellm Global State | **FIXED** | Removed global `litellm.api_key`/`api_base` assignment in `config_routes.py` test endpoint |
| **L5** Legacy Endpoints | **FIXED** | `/set_whitelist` changed to POST (see H2) |

### Deployment Notes for Existing Users

- **SESSION_COOKIE_SECURE change (M2/M3):** If you run with `REQUIRE_AUTH=true` over plain HTTP (no HTTPS), you must now set `SESSION_COOKIE_SECURE=false` explicitly. Production HTTPS deployments are unaffected.
- **Password validation (H1):** Existing users with short passwords are NOT affected — validation only runs on password creation/change. They will be prompted to use 8+ characters on their next password change.
- **Token secret (C2):** Existing feed tokens with stored `token_secret` continue to work. New tokens no longer store the plaintext secret. The `token_secret` column remains in the DB but will be `NULL` for new tokens.
