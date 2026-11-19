from __future__ import annotations

import re
from typing import Any

from flask import Response, current_app, g, jsonify, request, session

from app.auth.feed_tokens import FeedTokenAuthResult, authenticate_feed_token
from app.auth.service import AuthenticatedUser
from app.auth.state import feed_token_rate_limiter
from app.extensions import db
from app.models import User

SESSION_USER_KEY = "user_id"

# Paths that remain public even when auth is required.
_PUBLIC_PATHS: set[str] = {
    "/",
    "/health",
    "/robots.txt",
    "/manifest.json",
    "/favicon.ico",
    "/api/auth/login",
    "/api/auth/status",
    "/api/auth/discord/status",
    "/api/auth/discord/login",
    "/api/auth/discord/callback",
    "/api/landing/status",
    # Stripe webhooks must bypass auth to allow Stripe to deliver events
    "/api/billing/stripe-webhook",
}

_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/static/",
    "/assets/",
    "/images/",
    "/fonts/",
    "/.well-known/",
)

_PUBLIC_EXTENSIONS: tuple[str, ...] = (
    ".js",
    ".css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".txt",
)


_TOKEN_PROTECTED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^/feed/[^/]+$"),
    re.compile(r"^/feed/user/[^/]+$"),
    # Post GUIDs may contain "/" (routes use the ``path`` converter and
    # request.path is already percent-decoded), so match them with ``.+``.
    re.compile(r"^/api/posts/.+/(audio|download(?:/original)?)$"),
    re.compile(r"^/post/.+(?:\.mp3|/original\.mp3)$"),
)


def init_auth_middleware(app: Any) -> None:
    """Attach the authentication guard to the Flask app."""

    @app.before_request
    def enforce_authentication() -> Response | None:
        if request.method == "OPTIONS":
            return None

        settings = current_app.config.get("AUTH_SETTINGS")
        if not settings or not settings.require_auth:
            return None

        if _is_public_request(request.path):
            return None

        client_identifier = request.remote_addr or "unknown"

        session_user = _load_session_user()
        if session_user is not None:
            g.current_user = session_user
            g.feed_token = None
            return None

        if _is_token_protected_endpoint(request.path):
            limiter_key = _feed_token_limiter_key(client_identifier)
            # Valid credentials bypass the limiter: anyone who knows a token id can
            # put it into backoff, and that must not lock out its owner. Secrets are
            # 144-bit random values, so guessing is not what the limiter defends;
            # it answers misbehaving clients with 429 instead of repeated 401s.
            token_result = _authenticate_feed_token_from_query()
            if token_result is not None:
                feed_token_rate_limiter.register_success(limiter_key)
                g.current_user = token_result.user
                g.feed_token = token_result
                return None

            retry_after = feed_token_rate_limiter.retry_after(limiter_key)
            if retry_after:
                return _too_many_requests(retry_after)

            backoff = feed_token_rate_limiter.register_failure(limiter_key)
            response = _token_unauthorized()
            if backoff:
                response.headers["Retry-After"] = str(backoff)
            return response

        return _json_unauthorized()


def _load_session_user() -> AuthenticatedUser | None:
    raw_user_id = session.get(SESSION_USER_KEY)
    if isinstance(raw_user_id, str) and raw_user_id.isdigit():
        user_id = int(raw_user_id)
    elif isinstance(raw_user_id, int):
        user_id = raw_user_id
    else:
        return None

    user = db.session.get(User, user_id)
    if user is None:
        session.pop(SESSION_USER_KEY, None)
        return None

    return AuthenticatedUser(id=user.id, username=user.username, role=user.role)


def _feed_token_limiter_key(client_identifier: str) -> str:
    """Throttle failures per presented token rather than per client address.

    Behind a reverse proxy or Docker's port proxy every client shares one
    address, so an address key lets a podcast app retrying stale URLs lock
    out every valid feed token. Guessing secrets for one token id is still
    throttled; requests without a token keep the address key.
    """
    token_id = request.args.get("feed_token")
    if token_id:
        # Real token ids are 32 characters; truncation only bounds key size.
        return f"feed_token:{token_id[:64]}"
    return client_identifier


def _is_token_protected_endpoint(path: str) -> bool:
    return any(pattern.match(path) for pattern in _TOKEN_PROTECTED_PATTERNS)


def _authenticate_feed_token_from_query() -> FeedTokenAuthResult | None:
    token_id = request.args.get("feed_token")
    secret = request.args.get("feed_secret")
    if not token_id or not secret:
        return None

    return authenticate_feed_token(token_id, secret, request.path)


def _is_public_request(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True

    if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return True

    if any(path.endswith(ext) for ext in _PUBLIC_EXTENSIONS):
        return True

    return False


def _json_unauthorized(message: str = "Authentication required.") -> Response:
    response = jsonify({"error": message})
    response.status_code = 401
    return response


def _token_unauthorized() -> Response:
    response = Response("Invalid or missing feed token", status=401)
    return response


def _too_many_requests(retry_after: int) -> Response:
    response = Response("Too Many Authentication Attempts", status=429)
    response.headers["Retry-After"] = str(retry_after)
    return response
