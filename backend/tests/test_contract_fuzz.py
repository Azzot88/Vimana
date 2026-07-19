"""T_TEST.4 — schemathesis contract fuzz.

Runs schemathesis in-process against the FastAPI app (ASGI transport, no
external server needed). For every endpoint declared in `/openapi.json`,
schemathesis generates a batch of Hypothesis-style inputs and hits the
endpoint. We assert: **no unhandled 500s**.

Auth-required endpoints are called without a token; they should return
401/403 (declared status codes), not 500. If they return 500, it's a real
bug — validation is probably running before auth check, or the handler
crashes on missing user.

MVP scope:
- `not_a_server_error` check only (skip response_schema_conformance for
  pt.1 — OpenAPI is auto-generated and may have gaps).
- `max_examples=15` per endpoint (fast for local + CI).
- ~50 endpoints × 15 examples ≈ 750 requests ≈ 15-30 sec.

pt.2 follow-ups:
- authenticated fuzz (inject Bearer token via schemathesis hooks).
- full checks (response_schema, status_code_conformance, content_type).
- HTML report artifact.
- OpenAPI drift check vs frontend TS types (`openapi-typescript`).
"""
from __future__ import annotations

import pytest
import schemathesis
from hypothesis import settings

from app.main import app

# EXPOSE_DOCS=false hides /openapi.json at the HTTP layer, but FastAPI still
# generates the schema in memory — `app.openapi()` returns it as a dict.
# Passing `app=app` tells schemathesis to route calls through ASGI.
#
# FastAPI defaults to OpenAPI 3.1.0; schemathesis 3.39 only fully supports
# 3.0.x. We downgrade the version string + force the 3.0 loader. Any true
# 3.1-only features (e.g. `type: [string, null]`) would trip the fuzzer —
# we haven't hit any yet.
_raw_schema = app.openapi()
_raw_schema["openapi"] = "3.0.3"
schema = schemathesis.from_dict(_raw_schema, app=app, force_schema_version="30")


@schema.parametrize()
@settings(max_examples=15, deadline=None)
def test_no_server_errors(case):
    """No endpoint returns 500 for any generated input.

    `deadline=None` because Hypothesis's default 200ms deadline is too tight
    for ASGI + DB roundtrips.
    """
    response = case.call_asgi()
    assert response.status_code < 500, (
        f"5xx from {case.method} {case.path}\n"
        f"  body: {case.body!r}\n"
        f"  query: {case.query!r}\n"
        f"  headers: {case.headers!r}\n"
        f"  response ({response.status_code}): {response.text[:400]}"
    )
