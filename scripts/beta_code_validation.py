"""
Server-side validation of MandarinOS beta codes against the MandarinOS.app
website's POST /api/beta/validate endpoint (server-to-server, Railway to
Vercel — no CORS needed, no participant identity ever crosses this
boundary).

Tri-state result, never a plain boolean: validate_beta_code() returns one
of "valid", "invalid", or "temporarily_unavailable". Callers (ui_server.py's
POST /api/beta_code/validate, and transitively ui/app.js) must never
collapse "temporarily_unavailable" into "valid" — that conflation was a
real defect in an earlier version of this module (it returned a plain
`True` for both a confirmed-active code AND an unreachable website,
making the two indistinguishable to the browser). Only an explicit,
well-formed `{"valid": true}` or `{"valid": false}` response from the
website is definitive; everything else — timeout, connection failure,
non-2xx status, malformed JSON, or an unexpected response shape — is
"temporarily_unavailable".

The website endpoint returns only a boolean — never name, email, or any
other identity field — so nothing privacy-sensitive is received, cached,
or logged here. Cache keys (beta codes) are never written to any log.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Optional

# Mirrors MandarinOS.app's lib/beta/code.ts BETA_CODE_PATTERN exactly.
# Kept in sync manually; a mismatch only causes an extra network round
# trip (this repo's regex is used for a cheap pre-check only — the
# website is always the source of truth).
_SAFE_BETA_CODE = re.compile(r"^MOS-BETA-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}$")

# Default to the www host: Vercel permanently redirects (308) the apex
# host mandarinos.app → www.mandarinos.app, and urllib.request does not
# follow 308 on POST, so using the apex URL makes every validation look
# like a transport failure (temporarily_unavailable). Prefer www unless
# MANDARINOS_WEBSITE_URL is set explicitly to a non-redirecting base.
_WEBSITE_BASE_URL = os.environ.get("MANDARINOS_WEBSITE_URL", "https://www.mandarinos.app").rstrip("/")
_VALIDATE_URL = f"{_WEBSITE_BASE_URL}/api/beta/validate"
_TIMEOUT_SECONDS = 3.0
_CACHE_TTL_SECONDS = 600  # 10 minutes — bounds how stale a revocation can be

VALID = "valid"
INVALID = "invalid"
TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"

# code (already uppercased/trimmed) -> (status, expires_at_monotonic)
# Only VALID/INVALID are ever stored here — see validate_beta_code().
_cache: dict = {}


def is_well_formed(code: str) -> bool:
    """Cheap client-independent format check, no network call."""
    return bool(code) and bool(_SAFE_BETA_CODE.match(code.strip()))


def validate_beta_code(code: str, *, _time_fn=time.monotonic) -> str:
    """Returns "valid", "invalid", or "temporarily_unavailable". Never raises.

    - Malformed input -> "invalid" immediately, no network call (rule C).
    - A definitive website response ("valid"/"invalid") is cached for
      _CACHE_TTL_SECONDS, so a page that re-checks on every load does not
      hammer the website.
    - Any transport/parse failure, timeout, or non-2xx status is
      "temporarily_unavailable" and is NEVER cached — the next call
      retries promptly rather than sticking on a guess (or on a stale
      negative that would otherwise outlive an outage).
    """
    if not is_well_formed(code):
        return INVALID

    normalized = code.strip()
    now = _time_fn()
    cached = _cache.get(normalized)
    if cached and cached[1] > now:
        return cached[0]

    result = _call_website(normalized)
    if result is None:
        return TEMPORARILY_UNAVAILABLE

    status = VALID if result else INVALID
    _cache[normalized] = (status, now + _CACHE_TTL_SECONDS)
    return status


def _call_website(code: str) -> Optional[bool]:
    """Returns True/False on a definitive, well-formed website response.
    Returns None (meaning: temporarily unavailable / indeterminate) for
    any network error, timeout, non-2xx HTTP status, or malformed/
    unexpected response body. Never raises."""
    try:
        payload = json.dumps({"betaCode": code}).encode("utf-8")
        req = urllib.request.Request(
            _VALIDATE_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            status_code = getattr(resp, "status", 200)
            raw = resp.read().decode("utf-8")
        if status_code < 200 or status_code >= 300:
            # Defensive: urlopen normally raises HTTPError for non-2xx
            # (caught below), but some environments/mocks may not.
            return None
        body = json.loads(raw)
        if isinstance(body, dict) and isinstance(body.get("valid"), bool):
            return body["valid"]
        # Well-formed HTTP response, but not the expected JSON shape —
        # treat as indeterminate rather than guessing either way.
        return None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    except Exception:
        # Defense in depth: this function must never raise into the caller.
        return None


def _reset_cache_for_tests() -> None:
    _cache.clear()
