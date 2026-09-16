"""ЭТАП 3.12 integrity — the cargo is written once and never edited.

`IMPLEMENTATIONPLAN §3.12.1`: «Груз создаётся один раз и не меняется». The check
the phase asked for is that a change is *refused*, not merely unbuilt — so this
asserts the shape of the API itself: no route can write a cargo except the
response that creates one, and the templates (a sender's own drafts) are a
different table on purpose.

Route introspection rather than a list of endpoints to remember, for the reason
`test_idor_matrix` gives: a new `PATCH /cargos/{id}` added next year fails this
file by the mere fact of existing.
"""
from __future__ import annotations

from fastapi.routing import APIRoute

from app.main import app

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

#: The two doors that may write a cargo, and why each one is allowed.
#: `deals/match` is the response that creates it (T3.12.03); the template
#: endpoints write `cargo_templates`, a sender's own drafts, which is a
#: different table and never touches a cargo in a deal.
ALLOWED = {
    "/api/deals/match",
    "/api/me/cargo-templates",
    "/api/me/cargo-templates/{template_id}",
}


def test_no_route_edits_a_cargo():
    offenders = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in ALLOWED:
            continue
        if not (WRITE_METHODS & route.methods):
            continue
        if "cargo" in route.path.lower():
            offenders.append(f"{sorted(route.methods)} {route.path}")
    assert offenders == [], f"a cargo can be written here: {offenders}"


async def test_the_terms_refuse_a_cargo_field(client, sender_headers, seed_deal):
    """The other way a cargo could have been edited: through the terms. T3.12.04
    closed it by name, and this is the refusal the integrity check asks for."""
    r = await client.post(
        f"/api/deals/{seed_deal.id}/terms",
        headers=sender_headers,
        json={
            "price_total": 50,
            "currency": "USD",
            "payment_method": "cash_on_delivery",
            "weight_kg": 2.0,
        },
    )
    assert r.status_code == 422, r.text
    assert "weight_kg" in r.text
