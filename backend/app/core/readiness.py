"""T_OPS.1 — stop taking traffic before stopping, so a deploy loses nothing.

**The measurement this exists for.** A load run started immediately after
`up -d --force-recreate backend` answered 1.8 % of requests with an error; the
same run on a warmed container answered 0 %. Every deploy drops whatever is in
flight. Today that costs somebody a reloaded list of trips. After Phase 4 the
same second lands on a payment confirmation.

**Liveness and readiness are different questions, and one endpoint cannot
answer both.** `/health` asks "is this process alive" — a supervisor restarts it
when the answer is no. `/ready` asks "should this process be given traffic" — a
balancer removes it from rotation when the answer is no, *without* restarting
anything. A process that is shutting down is alive and must not be given
traffic, which is exactly the state no single endpoint can express.

**The drain window is the point.** On `SIGTERM` this flips `/ready` to 503 and
then keeps serving normally for `DRAIN_SECONDS` before letting the server begin
its shutdown. A balancer notices within two or three failed checks and stops
sending new work; the requests already in flight finish because the process is
still running. Without the pause, "stop accepting" and "stop existing" happen in
the same instant and the balancer learns about it from the failures.

**Nothing here is specific to one cloud.** An HTTP endpoint and an environment
variable are what nginx `upstream`, HAProxy, Traefik, Kubernetes readiness
probes and every managed balancer read. There is no metadata service, no
lifecycle hook, no vendor SDK.

**Honest today, useful later.** The product currently runs one backend behind
one nginx with no health checking, so `/ready` changes nothing about routing
*yet* — the value today is the drain pause itself, which lets in-flight requests
finish. Said out loud rather than left as an implication, because a switch that
does nothing is the kind of thing that gets discovered later and mistaken for a
bug. `DRAIN_SECONDS=0` turns the pause off entirely for anyone who wants the old
behaviour.

Functions (PROJECT §6.2a):
- `is_ready()` — should this process be given traffic. Called by: `main.ready`.
- `begin_drain()` — flip to "no", idempotent. Called by: `_on_sigterm`, tests.
- `drain_seconds()` — how long to keep serving after saying no.
  Called by: `install`, tests.
- `install(loop)` — wire `SIGTERM` to the drain. Called by: `main.lifespan`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal

logger = logging.getLogger(__name__)

_ready = True

#: Long enough for a balancer to see two or three failed checks, short enough
#: that a deploy does not feel stuck. Overridden per deployment: a balancer
#: checking every 10 s needs more than one checking every 2 s.
DEFAULT_DRAIN_SECONDS = 5.0


def is_ready() -> bool:
    return _ready


def begin_drain() -> None:
    """Say "do not send me work". Does not stop anything already running."""
    global _ready
    if _ready:
        logger.info("readiness: draining — /ready now answers 503")
    _ready = False


def reset_for_tests() -> None:
    """Only tests call this. A process that has begun draining is on its way
    out, and giving production a way back would invite using it."""
    global _ready
    _ready = True


def drain_seconds() -> float:
    raw = os.getenv("DRAIN_SECONDS", "").strip()
    if not raw:
        return DEFAULT_DRAIN_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.warning("DRAIN_SECONDS=%r is not a number — using default", raw)
        return DEFAULT_DRAIN_SECONDS


def install(loop: asyncio.AbstractEventLoop) -> None:
    """Put the drain in front of the server's own SIGTERM handling.

    uvicorn installs `handle_exit` for `SIGTERM` before the application starts,
    so it is captured here and called at the end of the pause — the server then
    shuts down exactly as it always did, just later. Chaining rather than
    replacing matters: reimplementing the shutdown would mean owning a part of
    uvicorn that changes between versions.

    Failure to install is logged and swallowed. A missing drain makes deploys
    what they already are today; an exception at startup makes the service what
    it is not.
    """
    delay = drain_seconds()
    if delay <= 0:
        logger.info("readiness: DRAIN_SECONDS=0 — shutting down without a pause")
        return

    try:
        previous = signal.getsignal(signal.SIGTERM)

        async def _drain_then_exit() -> None:
            begin_drain()
            # Ordinary requests keep being served throughout: the loop is not
            # blocked, only this task is.
            await asyncio.sleep(delay)
            logger.info("readiness: drain over after %.1fs — handing over", delay)
            if callable(previous):
                previous(signal.SIGTERM, None)
            else:
                # No prior handler means nothing else will stop us. Raising the
                # default behaviour is better than a process that ignores
                # SIGTERM and waits to be killed.
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                os.kill(os.getpid(), signal.SIGTERM)

        loop.add_signal_handler(
            signal.SIGTERM, lambda: loop.create_task(_drain_then_exit())
        )
        logger.info("readiness: SIGTERM will drain for %.1fs before shutdown", delay)
    except (NotImplementedError, RuntimeError, ValueError) as exc:
        # `add_signal_handler` is unavailable on Windows and inside some test
        # runners. Not a reason to fail startup.
        logger.warning("readiness: could not install the drain handler: %s", exc)
