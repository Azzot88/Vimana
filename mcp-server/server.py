"""T_AGENT.1 pt.1 — Vimana MCP server.

Exposes two tools to AI agents (Claude Desktop / Claude Code / other MCP
clients): `list_trips` and `get_trip_details`. Both read via HTTP against
the same backend the frontend uses — no direct DB access, no privileged
credentials.

pt.2 will add `search_trips`, per-key rate-limit, and `MCP_API_KEY` auth.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

API_URL = os.getenv("VIMANA_API_URL", "http://backend:8000")


server = Server("vimana")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_trips",
            description=(
                "List active Vimana trips matching optional filters. "
                "Returns basic trip data (id, carrier, origin, destination, "
                "depart_at, capacity). Filter values are optional; omit any "
                "of them to broaden the search."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "IATA/ICAO airport code, e.g. 'SVO'",
                    },
                    "destination": {
                        "type": "string",
                        "description": "IATA/ICAO airport code, e.g. 'JFK'",
                    },
                    "date": {
                        "type": "string",
                        "description": "ISO-8601 date (YYYY-MM-DD)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max trips to return (1..100).",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="get_trip_details",
            description=(
                "Get full trip data plus carrier reputation (UBA score + "
                "trust tier) and Nostr event id if the trip was published."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "trip_id": {
                        "type": "string",
                        "description": "UUID of the trip.",
                    }
                },
                "required": ["trip_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    async with httpx.AsyncClient(base_url=API_URL, timeout=10.0) as http:
        if name == "list_trips":
            params: dict[str, Any] = {"limit": arguments.get("limit", 20)}
            for k in ("origin", "destination", "date"):
                if arguments.get(k):
                    params[k] = arguments[k]
            r = await http.get("/api/trips", params=params)
            r.raise_for_status()
            data = r.json()
            items = data.get("items", [])
            if not items:
                return [TextContent(type="text", text="No trips matched.")]
            summary = _summarize_trips(items)
            return [TextContent(type="text", text=summary)]

        if name == "get_trip_details":
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
            event = r.json()
            return [TextContent(type="text", text=_format_event(event))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]


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
