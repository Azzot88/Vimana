"""T_OPS.1 — readiness, and why it is not liveness.

The pair exists because a process that is shutting down is **alive** and must
**not** be given traffic, and no single endpoint can say both. Every test here
pins one half of that sentence.

Written even though nothing routes on `/ready` today: with one backend behind
one nginx there is no balancer to read it. That is exactly the condition under
which code rots unnoticed — `T_TEST.7` and the Telegram webhook are this
project's two records of what an unexercised branch is worth — so the branch is
exercised here instead of waiting for the deployment that will use it.
"""
import pytest

from app.core import readiness


@pytest.fixture(autouse=True)
def fresh():
    """Draining is one-way in production, so every test starts from ready."""
    readiness.reset_for_tests()
    yield
    readiness.reset_for_tests()


async def test_ready_by_default(client):
    resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


async def test_draining_answers_503(client):
    """A balancer reads the status code, not the body."""
    readiness.begin_drain()
    resp = await client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "draining"


async def test_liveness_stays_200_while_draining(client):
    """The whole point of two endpoints. A supervisor watching `/health` must
    not restart a process that is deliberately shutting down — that would cut
    off the very requests the drain exists to finish."""
    readiness.begin_drain()
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/ready")).status_code == 503


async def test_the_rest_of_the_api_keeps_working_while_draining(client):
    """Draining means "send me no *new* work", not "stop working". A process
    that stopped answering would drop exactly what the drain is protecting."""
    readiness.begin_drain()
    assert (await client.get("/api/categories")).status_code == 200


def test_draining_is_idempotent():
    readiness.begin_drain()
    readiness.begin_drain()
    assert readiness.is_ready() is False


# ── the window ───────────────────────────────────────────────────────────────


def test_drain_seconds_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("DRAIN_SECONDS", raising=False)
    assert readiness.drain_seconds() == readiness.DEFAULT_DRAIN_SECONDS


def test_drain_seconds_reads_the_environment(monkeypatch):
    monkeypatch.setenv("DRAIN_SECONDS", "12.5")
    assert readiness.drain_seconds() == 12.5


def test_zero_disables_the_pause(monkeypatch):
    """Somebody who wants the old behaviour should be able to say so."""
    monkeypatch.setenv("DRAIN_SECONDS", "0")
    assert readiness.drain_seconds() == 0.0


def test_a_negative_window_is_not_a_negative_wait(monkeypatch):
    monkeypatch.setenv("DRAIN_SECONDS", "-3")
    assert readiness.drain_seconds() == 0.0


def test_nonsense_falls_back_rather_than_raising(monkeypatch):
    """A typo in `.env` must not stop the service from starting. It is a deploy
    setting, and refusing to boot over it would turn a slow shutdown into no
    service at all."""
    monkeypatch.setenv("DRAIN_SECONDS", "soon")
    assert readiness.drain_seconds() == readiness.DEFAULT_DRAIN_SECONDS


# ── the signal wiring ────────────────────────────────────────────────────────


async def test_sigterm_drains_before_handing_over(monkeypatch):
    """The order is the feature: `/ready` must go 503 *first*, and the server's
    own shutdown must happen only after the window has passed."""
    import asyncio
    import signal

    handed_over = asyncio.Event()
    monkeypatch.setattr(
        readiness.signal, "getsignal", lambda _sig: (lambda *_: handed_over.set())
    )
    monkeypatch.setenv("DRAIN_SECONDS", "0.05")

    loop = asyncio.get_running_loop()
    readiness.install(loop)

    signal.raise_signal(signal.SIGTERM)
    # asyncio delivers signals through a self-pipe, so the callback lands on a
    # later iteration of the loop rather than inside `raise_signal`.
    await asyncio.sleep(0.01)

    assert readiness.is_ready() is False, "readiness flips immediately"
    assert not handed_over.is_set(), "shutdown must wait for the window"

    await asyncio.wait_for(handed_over.wait(), timeout=2)

    # Put the loop's handler back so a later test is not shut down by ours.
    loop.remove_signal_handler(signal.SIGTERM)


async def test_a_zero_window_installs_nothing(monkeypatch):
    """With no pause there is nothing to chain, and replacing the server's own
    handler with one that only calls it would be a moving part for free."""
    import asyncio

    monkeypatch.setenv("DRAIN_SECONDS", "0")
    installed = []
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", lambda *a: installed.append(a))

    readiness.install(loop)
    assert installed == []
