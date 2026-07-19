# Vimana MCP server (T_AGENT.1)

Model Context Protocol server exposing Vimana trip data to AI agents (Claude
Desktop, Claude Code, other MCP-compatible clients).

## Tools (pt.1)

- `list_trips(origin?, destination?, date_from?, date_to?, category?)` — list
  active trips matching filters. Returns id, carrier_name, origin,
  destination, depart_at, capacity, allowed_categories.
- `get_trip_details(trip_id)` — full trip + carrier UBA + Nostr event id if
  published.

## pt.2 (deferred)

- `search_trips(text_query)` — full-text over destination + category.
- Rate-limit per API key.
- Auth via `MCP_API_KEY` env (currently open — bind on localhost only).
- Metrics `mcp_tool_call_count` per tool.

## Run

Under docker-compose profile `mcp` — not started by default:

```bash
docker compose --profile mcp up -d mcp-server
```

Then in Claude Desktop config:

```json
{
  "mcpServers": {
    "vimana": {
      "command": "docker",
      "args": ["exec", "-i", "vimana-mcp-server-1", "python", "/app/server.py"]
    }
  }
}
```

## Backend contract

Reads via HTTP against the same backend as the frontend:
`VIMANA_API_URL` (default `http://backend:8000` when in compose network).
