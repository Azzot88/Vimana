import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  listNotifications,
  markRead,
  unreadCount,
  type AppNotification,
} from '../api/notifications'
import { hrefFor, routeOf } from '../lib/notificationLinks'
import { useEventStream } from '../hooks/useEventStream'
import { useLiveBeat } from '../hooks/useLiveBeat'
import { usePrefs } from '../hooks/usePrefs'

/**
 * T_UX.29 pt.7 — the bell, and what is behind it.
 *
 * Owner, 2026-09-20: «Панель должна показывать обновления, произошедшие за
 * период неактивности. Если изменения произошли в активном окне, их статусы
 * показывать не нужно.»
 *
 * The second sentence is not implemented here and that is deliberate: a screen
 * that is showing something marks it read itself (`DealVaultPage` clears its
 * own deal on every beat). This component only reports what is left, which by
 * then is exactly what nobody saw. Putting the rule here instead would mean the
 * bell deciding what other screens are displaying.
 *
 * Fed by both mechanisms and for the same reason the deal screen is: the live
 * stream makes a press on the other side land at once, and the beat is the
 * floor under a connection that can die without saying so.
 *
 * Functions (PROJECT §6.2a):
 * - `NotificationBell()` — default export. Called by: `components/Navbar`.
 */
export default function NotificationBell() {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<AppNotification[]>([])
  const boxRef = useRef<HTMLDivElement>(null)

  const refreshCount = async () => {
    try {
      const { data } = await unreadCount()
      setUnread(data.unread)
    } catch {
      // A bell that cannot count is a bell that says nothing, not one that
      // shouts an error over the screen somebody is working on.
    }
  }

  const loadList = async () => {
    try {
      const { data } = await listNotifications()
      setItems(data)
    } catch {
      setItems([])
    }
  }

  useEffect(() => {
    void refreshCount()
  }, [])
  useLiveBeat(() => void refreshCount())
  useEventStream(() => {
    void refreshCount()
    if (open) void loadList()
  })

  // Closing on an outside click, like every other popover here. Pointerdown
  // rather than click: a click that lands on a link inside would otherwise
  // reach the handler after navigation had already begun.
  useEffect(() => {
    if (!open) return
    const onPointer = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    return () => document.removeEventListener('pointerdown', onPointer)
  }, [open])

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next) await loadList()
  }

  /** Marking everything seen is a separate press, never the act of opening:
   *  somebody who opens the panel to glance at it and closes it again has not
   *  dealt with anything, and a list that empties itself on sight cannot be
   *  re-read by the person who was too quick. */
  const readAll = async () => {
    try {
      const { data } = await markRead({})
      setUnread(data.unread)
      await loadList()
    } catch {
      // Nothing to say: the count refreshes on the next beat anyway.
    }
  }


  return (
    <div className="relative" ref={boxRef}>
      <button
        type="button"
        onClick={toggle}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t('notifications.bell') as string}
        className="relative w-9 h-9 rounded-field border border-navy/15 text-navy/60 hover:border-cyan hover:text-navy transition-colors"
      >
        <span aria-hidden>🔔</span>
        {unread > 0 && (
          <span
            /* The number, not a dot: «есть что-то» and «девять штук» are
               different facts, and only the second one makes somebody open it
               now rather than later. */
            className="absolute -top-1 -right-1 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-amber text-navy text-[10px] font-mono font-semibold flex items-center justify-center"
          >
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t('notifications.bell') as string}
          className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto rounded-card border border-navy/15 bg-white shadow-lift p-3 z-popover"
        >
          <div className="flex items-center justify-between gap-2 mb-2">
            <h3 className="text-sm font-display font-semibold text-navy">
              {t('notifications.title')}
            </h3>
            {unread > 0 && (
              <button
                type="button"
                onClick={readAll}
                className="text-[11px] font-body text-navy/50 hover:text-navy"
              >
                {t('notifications.readAll')}
              </button>
            )}
          </div>

          {items.length === 0 ? (
            /* «Ничего не пропущено» and «не удалось загрузить» are different
               answers, but the second one has already been logged and retried;
               saying so in a popover would be alarming about a thing that
               fixes itself. */
            <p className="text-xs font-body text-navy/45 py-4 text-center">
              {t('notifications.empty')}
            </p>
          ) : (
            <ul className="space-y-1">
              {items.map((n) => (
                <li key={n.id}>
                  <Link
                    /* T_UX.31 — decided by what the row is about, in one place
                       (`lib/notificationLinks`); it used to fall through to
                       `/notifications`, which is not an address. */
                    to={hrefFor(n)}
                    onClick={() => setOpen(false)}
                    className={`block rounded-field px-2 py-2 hover:bg-navy/5 ${
                      n.read_at ? 'opacity-60' : ''
                    }`}
                  >
                    <span className="block text-xs font-body text-navy">
                      {t(`notifications.kind.${n.kind.replace('.', '_')}`, n.kind)}
                    </span>
                    {/* The corridor, when the row carries one: «запрос по
                        вашему коридору» without naming which is a line you
                        have to open to understand. */}
                    {routeOf(n) && (
                      <span className="block text-[11px] font-mono text-navy/60">
                        {routeOf(n)}
                      </span>
                    )}
                    <span className="block text-[11px] font-body text-navy/40">
                      {prefs.since(n.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
