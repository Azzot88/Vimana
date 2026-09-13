import { useEffect, useRef } from 'react'

/** How often a live screen asks whether the other side has moved.
 *
 *  Ten seconds: fast enough that «подтвердил» lands while the other person is
 *  still looking at the screen, slow enough that two people watching one deal
 *  cost twelve requests a minute between them. Nobody is typing at anybody here
 *  — that is what the chat's own rhythm is for — so sub-second freshness would
 *  be paying a socket's complexity for an illusion of liveness.
 */
export const LIVE_BEAT_MS = 10 * 1000

/**
 * T3.11.27 — the other side moves too (owner, 2026-09-12).
 *
 * A deal is two people acting in turn, and a screen that only learns anything
 * when **this** person does something leaves the other half of every exchange
 * invisible: the carrier confirms a handover and the sender sits looking at
 * «ждём подтверждения» until they think to reload. A screen that is only right
 * after F5 is a screen nobody trusts.
 *
 * Polling rather than a socket, deliberately. The whole exchange is a handful of
 * acts over days, not a stream; a socket would be a second transport to
 * authenticate, keep alive, reconnect and reason about behind nginx — real
 * complexity bought for a screen that needs to be a few seconds fresh. When
 * something here genuinely needs sub-second, this is the thing to replace, and
 * replacing it in one file is the reason it is a hook rather than a second
 * `setInterval` copied into the next page.
 *
 * Paused while the tab is hidden. A backgrounded screen polling all afternoon
 * spends somebody's battery and our rate limit to answer a question nobody is
 * asking; `visibilitychange` also fires on the way back, so returning to the tab
 * refreshes at once rather than waiting out the interval.
 *
 * The callback is held in a ref on purpose: it is rebuilt on every render by
 * every caller, and putting it in the dependency list would tear the interval
 * down and start it again ten times a second — a timer that never fires.
 *
 * Functions (PROJECT §6.2a):
 * - `useLiveBeat(beat, active?, ms?)` — run `beat` while the tab is visible.
 *   Called by: `pages/DealVaultPage`, `pages/ChatPage`.
 */
export function useLiveBeat(
  beat: () => void,
  active: boolean = true,
  ms: number = LIVE_BEAT_MS,
): void {
  const ref = useRef(beat)
  ref.current = beat

  useEffect(() => {
    if (!active) return
    const fire = () => {
      if (document.visibilityState !== 'visible') return
      ref.current()
    }
    const timer = window.setInterval(fire, ms)
    document.addEventListener('visibilitychange', fire)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', fire)
    }
  }, [active, ms])
}
