"""T_AGENT.1 pt.2 — Vimana MCP server.

Exposes tools to AI agents (Claude Desktop / Claude Code / other MCP
clients). Reads via HTTP against the same backend the frontend uses — no
direct DB access, no privileged credentials.

pt.2 additions:
  - Optional `MCP_API_KEY` env: when set, every tool call must include a
    matching `api_key` argument. When empty, all calls proceed (dev mode).
  - Rate-limit 60 calls/minute per API key (or per-process when unauthed).
  - `search_trips(query)` — client-side substring search over listed trips.
    Real full-text via Nostr subscribe backfeed is pt.3.
  - Per-tool call counters exposed via `get_mcp_metrics`.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

API_URL = os.getenv("VIMANA_API_URL", "http://backend:8000")
REQUIRED_API_KEY = os.getenv("MCP_API_KEY", "").strip() or None
RATE_LIMIT_PER_MIN = int(os.getenv("MCP_RATE_LIMIT", "60"))
_WINDOW_SEC = 60.0

# In-process state. Single MCP process per stdio client — no need for Redis.
_calls_per_key: dict[str, deque[float]] = defaultdict(deque)
_metrics: dict[str, int] = defaultdict(int)
_metrics_rejected: dict[str, int] = defaultdict(int)


server = Server("vimana")


def _check_auth_and_rate_limit(tool_name: str, api_key: str | None) -> str | None:
    """Returns error string if request should be rejected, else None. Also
    trims the rate-limit window and bumps counters."""
    if REQUIRED_API_KEY is not None:
        if not api_key or api_key != REQUIRED_API_KEY:
            _metrics_rejected["auth"] += 1
            return "Unauthorized: valid `api_key` argument required."
    bucket_key = api_key or "_anon"
    now = time.monotonic()
    bucket = _calls_per_key[bucket_key]
    while bucket and bucket[0] < now - _WINDOW_SEC:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        _metrics_rejected["rate_limit"] += 1
        return (
            f"Rate limit exceeded: {RATE_LIMIT_PER_MIN} calls/min per key. "
            f"Try again in ~{int(_WINDOW_SEC - (now - bucket[0]))}s."
        )
    bucket.append(now)
    _metrics[tool_name] += 1
    return None


@server.list_tools()
async def list_tools() -> list[Tool]:
    auth_prop = (
        {
            "api_key": {
                "type": "string",
                "description": "MCP API key (required by this deployment).",
            }
        }
        if REQUIRED_API_KEY is not None
        else {}
    )
    return [
        Tool(
            name="list_trips",
            description=(
                "List active Vimana trips matching optional filters. "
                "Returns basic trip data (id, carrier, origin, destination, "
                "depart_at, capacity). Omit filters to broaden the search."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    **auth_prop,
                    "origin": {"type": "string", "description": "IATA/ICAO code, e.g. 'SVO'"},
                    "destination": {"type": "string", "description": "IATA/ICAO code, e.g. 'JFK'"},
                    "date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                    "limit": {"type": "integer", "description": "Max trips (1..100).", "default": 20},
                },
            },
        ),
        Tool(
            name="search_trips",
            description=(
                "Substring search over listed trips (origin, destination, "
                "carrier name, allowed categories). Pulls up to `limit` "
                "trips from the backend, then filters client-side. Full-text "
                "over Nostr subscribe backfeed is deferred to pt.3."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    **auth_prop,
                    "query": {"type": "string", "description": "Case-insensitive substring."},
                    "limit": {"type": "integer", "description": "Max to scan (1..200).", "default": 100},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_trip_details",
            description=(
                "Get full trip data plus carrier reputation (UBA + trust tier) "
                "and Nostr event id if the trip was published."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    **auth_prop,
                    "trip_id": {"type": "string", "description": "UUID of the trip."},
                },
                "required": ["trip_id"],
            },
        ),
        Tool(
            name="get_mcp_metrics",
            description="Per-tool call counters + rejection reasons for this MCP process.",
            inputSchema={
                "type": "object",
                "properties": auth_prop,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    api_key = arguments.get("api_key")
    err = _check_auth_and_rate_limit(name, api_key)
    if err is not None:
        return [TextContent(type="text", text=err)]

    async with httpx.AsyncClient(base_url=API_URL, timeout=10.0) as http:
        if name == "list_trips":
            return await _tool_list_trips(http, arguments)
        if name == "search_trips":
            return await _tool_search_trips(http, arguments)
        if name == "get_trip_details":
            return await _tool_get_trip_details(http, arguments)
        if name == "get_mcp_metrics":
            return _tool_metrics()
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _tool_list_trips(http: httpx.AsyncClient, arguments: dict) -> list[TextContent]:
    params: dict[str, Any] = {"limit": min(int(arguments.get("limit", 20)), 100)}
    for k in ("origin", "destination", "date"):
        if arguments.get(k):
            params[k] = arguments[k]
    r = await http.get("/api/trips", params=params)
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return [TextContent(type="text", text="No trips matched.")]
    return [TextContent(type="text", text=_summarize_trips(items))]


async def _tool_search_trips(http: httpx.AsyncClient, arguments: dict) -> list[TextContent]:
    query = (arguments.get("query") or "").strip().lower()
    if not query:
        return [TextContent(type="text", text="Empty query.")]
    limit = min(int(arguments.get("limit", 100)), 200)
    r = await http.get("/api/trips", params={"limit": limit})
    r.raise_for_status()
    items = r.json().get("items", [])
    matched = [t for t in items if _trip_matches(t, query)]
    if not matched:
        return [TextContent(type="text", text=f"No trips match '{query}' (scanned {len(items)}).")]
    return [TextContent(type="text", text=_summarize_trips(matched))]


async def _tool_get_trip_details(http: httpx.AsyncClient, arguments: dict) -> list[TextContent]:
    trip_id = arguments.get("trip_id")
    if not trip_id:
        return [TextContent(type="text", text="Missing trip_id.")]
    r = await http.get(f"/api/trips/{trip_id}/nostr-event")
    if r.status_code == 503:
        r2 = await http.get("/api/trips", params={"limit": 100})
        items = r2.json().get("items", [])
        match = next((t for t in items if t["id"] == trip_id), None)
        if not match:
            return [TextContent(type="text", text=f"Trip {trip_id} not found.")]
        return [TextContent(type="text", text=_format_trip(match))]
    r.raise_for_status()
    return [TextContent(type="text", text=_format_event(r.json()))]


def _tool_metrics() -> list[TextContent]:
    lines = ["MCP metrics (this process):"]
    for tool, count in sorted(_metrics.items()):
        lines.append(f"  {tool}: {count}")
    if _metrics_rejected:
        lines.append("Rejections:")
        for reason, count in sorted(_metrics_rejected.items()):
            lines.append(f"  {reason}: {count}")
    lines.append(f"Auth required: {REQUIRED_API_KEY is not None}")
    lines.append(f"Rate limit: {RATE_LIMIT_PER_MIN}/min per key")
    return [TextContent(type="text", text="\n".join(lines))]


def _trip_matches(trip: dict, query: str) -> bool:
    fields = [
        trip.get("origin") or "",
        trip.get("destination") or "",
        trip.get("carrier_name") or "",
        " ".join(trip.get("allowed_categories") or []),
    ]
    haystack = " ".join(fields).lower()
    return query in haystack


def _summarize_trips(items: list[dict]) -> str:
    lines = [f"{len(items)} trip(s):"]
    for t in items[:20]:
        carrier_name = t.get("carrier_name") or "unknown"
        uba = t.get("carrier_uba")
        uba_str = f" · UBA {uba}" if uba is not None else ""
        cats = ", ".join(t.get("allowed_categories") or [])
        lines.append(
            f"- {t.get('id', '?')[:8]}: {t.get('origin')}→{t.get('destination')} "
            f"@ {t.get('depart_at', '')[:16]} · {t.get('capacity')}kg · "
            f"{carrier_name}{uba_str} · [{cats}]"
        )
    return "\n".join(lines)


def _format_trip(trip: dict) -> str:
    return (
        f"Trip {trip.get('id')}:\n"
        f"  {trip.get('origin')} → {trip.get('destination')}\n"
        f"  Depart: {trip.get('depart_at')}\n"
        f"  Capacity: {trip.get('capacity')} kg\n"
        f"  Categories: {', '.join(trip.get('allowed_categories') or [])}\n"
        f"  Carrier: {trip.get('carrier_name')}\n"
        f"  UBA: {trip.get('carrier_uba') or 'not computed'} "
        f"({trip.get('carrier_uba_level') or '-'})\n"
        f"  Nostr event: {trip.get('nostr_event_id') or 'not published'}\n"
    )


def _format_event(event: dict) -> str:
    return (
        f"Nostr event {event.get('id')}\n"
        f"  Kind: {event.get('kind')}\n"
        f"  Pubkey: {event.get('pubkey')}\n"
        f"  Signed at: {event.get('created_at')}\n"
        f"  Content: {event.get('content')[:200]}\n"
    )


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
