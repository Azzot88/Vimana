"""T_UX.29 pt.3 — the second mechanism, beside the ten-second beat.

Owner, 2026-09-20: «Каждые 10 секунд хорошо, но лучше когда на той стороне
нажали кнопку или что-то изменили, это передавалось другой стороне… Создай
второй механизм дополнительно к 10 секундам.»

Server-sent events over Redis pub/sub. One stream per signed-in person, carrying
everything addressed to them (`core.notify.channel_for`), so a tab subscribes
once and both the bell and the open deal screen feed from it.

**Why this and not a socket.** The traffic is one-way — the server has news, the
client has nothing to say back that is not already a request — and SSE is that
shape exactly: an ordinary GET that never ends, through the same nginx, the same
JWT, the same rate limits. A WebSocket would be a second transport to
authenticate, keep alive and reason about behind a proxy, bought for a direction
we do not use.

**Why the beat stays.** This connection can be dropped by anything between here
and the browser — a proxy timeout, a sleeping laptop, a phone changing networks —
and none of those announce themselves. The poll is the floor: worst case the
screen is ten seconds stale, which is where it was before this file existed. A
live channel that is trusted alone is a live channel that silently stops.

`X-Accel-Buffering: no` is not decoration: nginx buffers proxied responses by
default, and a buffered stream is a stream that arrives in one piece when it
ends — which for a connection that never ends means never.

Functions (PROJECT §6.2a):
  - `stream(...)` — the SSE endpoint. Called by: `frontend/src/hooks/useEventStream`.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.core.notify import channel_for
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

#: How long to wait for news before sending a comment line. Two jobs: it keeps
#: proxies from closing an idle connection as dead, and it is when we notice the
#: client has gone — `await` on a closed socket does not raise until we write.
_HEARTBEAT_SECONDS = 20


@router.get("/events/stream")
async def stream(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Everything addressed to this person, as it happens."""
    from app.core.redis_client import get_client

    async def body():
        pubsub = None
        try:
            pubsub = get_client().pubsub()
            await pubsub.subscribe(channel_for(current_user.id))
            # Said once, immediately: a client that has opened the stream should
            # not have to guess whether it worked from the absence of news.
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=_HEARTBEAT_SECONDS
                )
                if message is None:
                    # A comment line. Invisible to `EventSource` and to any
                    # reader that follows the spec, and enough to keep the
                    # connection from being collected as idle.
                    yield ": keep-alive\n\n"
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", "replace")
                if not isinstance(data, str):
                    continue
                try:
                    json.loads(data)
                except ValueError:
                    continue
                yield f"event: notification\ndata: {data}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the poll is the floor
            logger.warning("event stream ended early", exc_info=True)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.aclose()
                except Exception:  # noqa: BLE001
                    pass

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx buffers proxied responses by default; a buffered stream that
            # never ends is a stream that never arrives.
            "X-Accel-Buffering": "no",
        },
    )
