"""T_SEC.6 — the address our own nginx saw, not the one the caller typed.

`X-Forwarded-For` is a list anyone may prepend to. A request arriving with
`X-Forwarded-For: 1.2.3.4` gets that value appended to by nginx
(`$proxy_add_x_forwarded_for`), so the header the application receives reads
`1.2.3.4, <real client>`. Reading it **left to right** — which is what this
project did until now — means reading the attacker's own string.

Two things were built on that reading, and both were wrong for the same reason:

- the rate limiter keyed its counters on it, so every limit in the product was
  one header away from being unlimited;
- `T_SEC.6` was about to put it in a letter, which would have let a stranger
  choose what the owner reads about the break-in.

**The rightmost element is the one nginx added itself**, and nginx is the only
proxy in front of the app — it is therefore the peer address of the connection
nginx accepted, and the only entry in the list that no caller could write.

If a CDN is ever put in front (Cloudflare was one of the geolocation options
considered and rejected), this becomes wrong in the other direction: the
rightmost element would be the CDN's edge, and the real client would sit one
place to the left. That is a one-line change here — count the trusted hops — and
it is named so the next person finds it before the counters lie again.

Functions (PROJECT §6.2a):
- `client_ip(request) -> str` — the trusted address, or the direct peer when
  there is no proxy in front (dev, tests).
  Called by: `core/rate_limit._key_func`, `core/sign_ins.record`.
"""
from __future__ import annotations

import ipaddress


def client_ip(request) -> str:
    """The caller's address as observed by our own infrastructure."""
    hops = [part.strip() for part in request.headers.get("X-Forwarded-For", "").split(",")]
    hops = [hop for hop in hops if hop]
    if hops:
        try:
            # Parsed rather than trusted: a header is a string, and everything
            # downstream — a Redis key, a letter, a network mask — assumes an
            # address. A malformed last hop falls through to the peer address
            # rather than becoming the key it was pretending to be.
            return str(ipaddress.ip_address(hops[-1]))
        except ValueError:
            pass

    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"
