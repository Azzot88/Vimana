# Vimana MCP server (T_AGENT.1)

Model Context Protocol server exposing Vimana trip data to AI agents (Claude
Desktop, Claude Code, other MCP-compatible clients).

## Tools

- **`list_trips(origin?, destination?, date?, limit?)`** — filter-based
  listing. Returns id, carrier_name, origin, destination, depart_at,
  capacity, allowed_categories, carrier UBA.
- **`search_trips(query, limit?)`** — case-insensitive substring search over
  origin / destination / carrier_name / categories. Scans up to `limit`
  trips (max 200) client-side. Real full-text via Nostr subscribe backfeed
  is pt.3.
- **`get_trip_details(trip_id)`** — full trip + carrier UBA + Nostr event id.
- **`get_mcp_metrics()`** — per-tool call counters + rejection reasons for
  this MCP process. Useful for observability and debugging.

All tools accept an optional `api_key` argument (see Auth below).

## Auth (pt.2)

Opt-in. Set `MCP_API_KEY` in the container env:

```yaml
environment:
  MCP_API_KEY: <32-char-random>
```

When set, every tool call must include `api_key` matching this value.
Unauthed calls return `"Unauthorized: valid api_key argument required."`
When unset (default), all calls proceed — fine for local dev when the
subprocess is trusted.

## Rate limit (pt.2)

Per-key sliding window (60 sec). Default `60 calls/min`, override via
`MCP_RATE_LIMIT` env. Rejections show remaining seconds until the window
clears.

## Metrics (pt.2)

In-process counters, no external dependency. Call `get_mcp_metrics` from an
agent to inspect. Persistence across restarts / cross-process aggregation
is a pt.3 concern.

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
No DB creds, no privileged access — MCP sees only what a logged-out browser
would.

## pt.3 (deferred)

- Full-text `search_trips` via Nostr subscribe backfeed (Nostr publish
  currently off — see `NOSTR_PUBLISH_ENABLED`).
- Metrics persistence in Postgres or Prometheus scrape endpoint.
- Per-user MCP tokens tied to Vimana accounts (e.g., "my trips only").
- SSE transport for remote MCP (currently stdio-only).
