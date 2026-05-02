"""Provider-agnostic key-rotating reverse proxy.

Speaks any OpenAI-compatible upstream (Groq, OpenRouter, OpenAI, ...). Rotates
Authorization across N keys round-robin. On 429 from upstream, marks the
chosen key as cooling-down (using the upstream's retry-after hint) and retries
the request with the next non-cooled key. If ALL keys are cooling, blocks
until the soonest one is free again, up to MAX_WAIT_SEC. This lets long jobs
complete by pacing through rolling-window limits across N independent accounts.

Environment:
- UPSTREAM_BASE_URL   default https://api.groq.com  (also accepts legacy GROQ_UPSTREAM)
- API_KEYS            comma-separated bearer tokens (also accepts legacy GROQ_KEYS)
- UPSTREAM_TIMEOUT_SEC default 600
- MAX_WAIT_SEC        default 3300
"""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response

UPSTREAM_BASE_URL = os.environ.get(
    "UPSTREAM_BASE_URL", os.environ.get("GROQ_UPSTREAM", "https://api.groq.com")
).rstrip("/")
KEYS = [
    k.strip()
    for k in os.environ.get("API_KEYS", os.environ.get("GROQ_KEYS", "")).split(",")
    if k.strip()
]
TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT_SEC", "600"))
MAX_WAIT_SEC = float(os.environ.get("MAX_WAIT_SEC", "3300"))
INJECT_REASONING_EXCLUDE = os.environ.get("INJECT_REASONING_EXCLUDE", "").lower() in {
    "1", "true", "yes",
}

if not KEYS:
    raise SystemExit(
        "API_KEYS env var required (comma-separated bearer tokens)"
    )

log = logging.getLogger("key-fanout")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

cooldowns: dict[str, float] = {k: 0.0 for k in KEYS}
_rr = itertools.cycle(range(len(KEYS)))
_lock = asyncio.Lock()


def _parse_retry_after(value: str) -> float:
    """Upstreams sometimes return retry-after as plain seconds, sometimes as '11m47s'."""
    if not value:
        return 30.0
    try:
        return float(value)
    except ValueError:
        pass
    total = 0.0
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([dhms])", value.lower()):
        total += float(amount) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return total or 30.0


async def _pick_key(deadline: float) -> tuple[int, str] | None:
    """Return (index, key) of the next non-cooled key, blocking until one is free.
    Returns None if the deadline is reached first.
    """
    while True:
        async with _lock:
            now = time.time()
            for _ in range(len(KEYS)):
                idx = next(_rr)
                key = KEYS[idx]
                if cooldowns[key] <= now:
                    return idx, key
            soonest = min(cooldowns.values())
        wait = soonest - time.time()
        if wait <= 0:
            continue
        if time.time() + wait > deadline:
            log.warning("all keys cooling, deadline would be exceeded — giving up")
            return None
        sleep_for = min(wait + 0.5, 30.0)
        log.warning(
            "all keys cooling — sleeping %.0fs (soonest free in %.0fs)",
            sleep_for, wait,
        )
        await asyncio.sleep(sleep_for)


async def _set_cooldown(key: str, retry_after_sec: float) -> None:
    async with _lock:
        cooldowns[key] = max(cooldowns[key], time.time() + retry_after_sec)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info(
        "key-fanout up | keys=%d | upstream=%s | max_wait=%.0fs",
        len(KEYS), UPSTREAM_BASE_URL, MAX_WAIT_SEC,
    )
    yield


app = FastAPI(lifespan=lifespan)

_HOP_BY_HOP = {
    "host",
    "authorization",
    "content-length",
    "connection",
    "transfer-encoding",
    "content-encoding",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
}


@app.get("/healthz")
async def healthz() -> dict:
    now = time.time()
    return {
        "keys": len(KEYS),
        "upstream": UPSTREAM_BASE_URL,
        "cooldowns_sec": {
            f"key_{i}": max(0.0, cooldowns[KEYS[i]] - now) for i in range(len(KEYS))
        },
    }


@app.api_route(
    "/{path:path}",
    methods=["POST", "GET", "PUT", "DELETE", "PATCH"],
)
async def proxy(path: str, request: Request) -> Response:
    body = await request.body()
    in_headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}

    if (
        INJECT_REASONING_EXCLUDE
        and request.method == "POST"
        and "application/json" in request.headers.get("content-type", "").lower()
        and path.endswith("chat/completions")
        and body
    ):
        try:
            obj = json.loads(body)
            if isinstance(obj, dict):
                reasoning = obj.setdefault("reasoning", {})
                if isinstance(reasoning, dict) and "exclude" not in reasoning:
                    reasoning["exclude"] = True
                    body = json.dumps(obj).encode()
                    log.info("injected reasoning.exclude=true (path=%s)", path)
        except Exception as exc:
            log.warning("body mutation skipped: %s", exc)

    upstream_url = f"{UPSTREAM_BASE_URL}/{path}"
    deadline = time.time() + MAX_WAIT_SEC
    last_response: httpx.Response | None = None
    attempt = 0

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while True:
            attempt += 1
            picked = await _pick_key(deadline)
            if picked is None:
                if last_response is not None:
                    break
                return Response(
                    content=b'{"error":{"message":"all upstream keys exhausted",'
                            b'"type":"rate_limit_exceeded"}}',
                    status_code=429,
                    media_type="application/json",
                )
            idx, key = picked
            req_headers = dict(in_headers)
            req_headers["Authorization"] = f"Bearer {key}"
            log.info(
                "→ key#%d %s /%s (attempt %d, body=%dB)",
                idx, request.method, path, attempt, len(body),
            )
            r = await client.request(
                request.method,
                upstream_url,
                params=request.query_params,
                content=body,
                headers=req_headers,
            )
            last_response = r
            if r.status_code != 429:
                log.info("← key#%d HTTP %d", idx, r.status_code)
                break
            retry_after = _parse_retry_after(r.headers.get("retry-after", ""))
            try:
                err_msg = r.json().get("error", {}).get("message", "")
                m = re.search(r"try again in (\d+(?:\.\d+)?)([dhms])", err_msg.lower())
                if m:
                    retry_after = max(
                        retry_after,
                        float(m.group(1)) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[m.group(2)],
                    )
                m2 = re.search(r"try again in (\d+)m(\d+)s", err_msg.lower())
                if m2:
                    retry_after = max(
                        retry_after,
                        float(m2.group(1)) * 60 + float(m2.group(2)),
                    )
            except Exception:
                pass
            log.warning("← key#%d HTTP 429, cooling for %.0fs", idx, retry_after)
            await _set_cooldown(key, retry_after)

    assert last_response is not None
    out_headers = {k: v for k, v in last_response.headers.items() if k.lower() not in _HOP_BY_HOP}
    return Response(
        content=last_response.content,
        status_code=last_response.status_code,
        headers=out_headers,
        media_type=last_response.headers.get("content-type"),
    )
