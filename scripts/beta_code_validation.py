"""
Server-side validation of MandarinOS beta codes against the MandarinOS.app
website's POST /api/beta/validate endpoint (server-to-server, Railway to
Vercel — no CORS needed, no participant identity ever crosses this
boundary).

Fail-open by design: any network/timeout/parse error returns True (treat
the code as valid) so a transient website outage never strips a
legitimate participant's beta_code from their session data. Only an
explicit `{"valid": false}` response from the website is a definitive
"no" and clears the cached/attached code.

The website endpoint returns only a boolean — never name, email, or any
other identity field — so nothing privacy-sensitive is received, cached,
or logged here.
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

_WEBSITE_BASE_URL = os.environ.get("MANDARINOS_WEBSITE_URL", "https://mandarinos.app").rstrip("/")
_VALIDATE_URL = f"{_WEBSITE_BASE_URL}/api/beta/validate"
_TIMEOUT_SECONDS = 3.0
_CACHE_TTL_SECONDS = 600  # 10 minutes — bounds how stale a revocation can be

# code (already uppercased/trimmed) -> (valid, expires_at_monotonic)
_cache: dict = {}


def is_well_formed(code: str) -> bool:
    """Cheap client-independent format check, no network call."""
    return bool(code) and bool(_SAFE_BETA_CODE.match(code.strip()))


def validate_beta_code(code: str, *, _time_fn=time.monotonic) -> bool:
    """Returns True unless the website definitively reports the code invalid.

    Never raises. Results are cached per-code for _CACHE_TTL_SECONDS so a
    page that re-checks on every load does not hammer the website.
    """
    if not is_well_formed(code):
        return False

    normalized = code.strip()
    now = _time_fn()
    cached = _cache.get(normalized)
    if cached and cached[1] > now:
        return cached[0]

    result = _call_website(normalized)
    if result is None:
        # Unknown/transient outcome: fail open, and do not cache it, so
        # the next check retries soon rather than sticking on a guess.
        return True

    _cache[normalized] = (result, now + _CACHE_TTL_SECONDS)
    return result


def _call_website(code: str) -> Optional[bool]:
    """Returns True/False on a definitive website response, None on any failure."""
    try:
        payload = json.dumps({"betaCode": code}).encode("utf-8")
        req = urllib.request.Request(
            _VALIDATE_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
        body = json.loads(raw)
        if isinstance(body, dict) and isinstance(body.get("valid"), bool):
            return body["valid"]
        return None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    except Exception:
        # Defense in depth: this function must never raise into the caller.
        return None


def _reset_cache_for_tests() -> None:
    _cache.clear()
