import { useEffect, useRef } from 'react'

/** T_UX.29 pt.3 — the live half, beside the ten-second beat.
 *
 * Owner, 2026-09-20: «лучше, когда на той стороне нажали кнопку или что-то
 * изменили, это передавалось другой стороне… Создай второй механизм
 * дополнительно к 10 секундам.»
 *
 * **`fetch`, not `EventSource`.** The native one cannot set a header, and this
 * API authenticates with a bearer token; the alternative is the token in a query
 * string, where it lands in every access log between here and the server. A
 * streamed `fetch` is the same protocol with the header we need.
 *
 * **The beat is not replaced.** This connection can be dropped by a proxy
 * timeout, a sleeping laptop or a phone changing networks, and none of those
 * announce themselves. The poll is the floor — worst case the screen is ten
 * seconds stale, which is where it was before. A live channel trusted alone is a
 * live channel that silently stops.
 *
 * Reconnects with a widening delay, and only while the tab is visible: a
 * backgrounded tab holding a connection open all afternoon spends somebody's
 * battery to hear news nobody is reading. Coming back to the tab reconnects at
 * once, and the beat fires on the same event.
 *
 * Functions (PROJECT §6.2a):
 * - `useEventStream(onEvent, active?)` — call `onEvent` as news arrives.
 *   Called by: `components/NotificationBell`, `pages/DealVaultPage`.
 */
export interface LiveEvent {
  kind: string
  deal_id: string | null
  trip_id: string | null
}

export function useEventStream(
  onEvent: (event: LiveEvent) => void,
  active: boolean = true,
): void {
  const ref = useRef(onEvent)
  ref.current = onEvent

  useEffect(() => {
    if (!active || typeof window === 'undefined') return
    let stopped = false
    let controller: AbortController | null = null
    let retry = 0
    let timer: number | undefined

    const read = async () => {
      if (stopped || document.visibilityState !== 'visible') return
      const token = localStorage.getItem('token')
      if (!token) return
      controller = new AbortController()
      try {
        const res = await fetch('/api/events/stream', {
          headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
          signal: controller.signal,
        })
        if (!res.ok || !res.body) throw new Error(String(res.status))
        retry = 0
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        for (;;) {
          const { done, value } = await reader.read()
          if (done || stopped) break
          buffer += decoder.decode(value, { stream: true })
          /* SSE frames are separated by a blank line. Split on that and keep
             the tail: a chunk boundary can fall anywhere, including inside a
             frame, and parsing half of one would drop the whole event. */
          const frames = buffer.split('\n\n')
          buffer = frames.pop() ?? ''
          for (const frame of frames) {
            const line = frame
              .split('\n')
              .find((l) => l.startsWith('data:'))
            if (!line) continue
            try {
              const parsed = JSON.parse(line.slice(5).trim()) as LiveEvent
              if (parsed && typeof parsed.kind === 'string') ref.current(parsed)
            } catch {
              // A frame we cannot read is not a reason to drop the connection.
            }
          }
        }
      } catch {
        // Every ending looks the same from here — a closed laptop, a proxy, a
        // restarted backend — and the answer to all of them is to come back.
      } finally {
        controller = null
        if (!stopped) {
          retry = Math.min(retry + 1, 6)
          timer = window.setTimeout(read, 1000 * 2 ** retry)
        }
      }
    }

    const onVisible = () => {
      if (document.visibilityState !== 'visible') {
        controller?.abort()
        return
      }
      retry = 0
      window.clearTimeout(timer)
      void read()
    }

    void read()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      stopped = true
      window.clearTimeout(timer)
      controller?.abort()
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [active])
}
