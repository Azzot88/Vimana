import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { updateMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'

/** T3.32 — which kinds of event reach which channel.
 *
 *  Before this, a channel was on or off for everything: three switches, and the
 *  only way to quieten one thing was to quieten all of them. This is the same
 *  three channels, asked per class of event.
 *
 *  **The rows and columns come from the server, not from this file.** Which
 *  classes are shown (only those something actually sends) and which channels
 *  are live (`CHANNEL_*_ENABLED`) are decisions with one home in
 *  `core/notification_prefs`. A list hardcoded here would be a second copy free
 *  to drift — and drift here means offering somebody a switch for a message
 *  that never arrives.
 *
 *  Labels are the exception and have to be local: they are translations, and
 *  there are six of them per row.
 */
export default function NotificationMatrix() {
  const { t } = useTranslation()
  const { user, token, setAuth } = useAuthStore()
  const [busy, setBusy] = useState<string | null>(null)

  const prefs = user?.notification_prefs ?? {}
  const locked = new Set(user?.notification_locked ?? [])
  const classes = Object.keys(prefs)
  // Every row carries the same channels — the server fills the matrix in full,
  // so the first row is a safe place to read the column order from.
  const channels = Object.keys(prefs[classes[0]] ?? {})

  // Nothing to draw before /me answers, and nothing to draw for an account with
  // no live channel at all. An empty table with headers reads as broken.
  if (!classes.length || !channels.length) return null

  /** One cell, one request. The backend merges rather than assigns, so a click
   *  cannot disturb a row this screen is not even showing. */
  const toggle = async (eventClass: string, channel: string) => {
    if (!token || locked.has(eventClass)) return
    const cellKey = `${eventClass}:${channel}`
    setBusy(cellKey)
    try {
      const { data } = await updateMe({
        notification_prefs: { [eventClass]: { [channel]: !prefs[eventClass][channel] } },
      })
      setAuth(data, token)
    } catch {
      // Silent, and the cell snaps back on the next read: the switch reflects
      // what the server stored, never what was clicked.
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
      <div>
        <h2 className="font-display font-semibold text-base text-navy">
          {t('profile.notifications')}
        </h2>
        <p className="text-xs font-body text-navy/50 mt-1">
          {t('profile.matrix.hint')}
        </p>
      </div>

      {/* Scrolls inside itself rather than pushing the page sideways — three
          channels plus a label column is already wide on a phone. */}
      <div className="overflow-x-auto -mx-2 px-2">
        <table className="w-full min-w-[20rem] border-collapse">
          <thead>
            <tr>
              <th className="text-left pb-2" />
              {channels.map((channel) => (
                <th
                  key={channel}
                  scope="col"
                  className="pb-2 px-2 text-xs font-body font-medium text-navy/60 text-center whitespace-nowrap"
                >
                  {t(`profile.matrix.channel.${channel}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {classes.map((eventClass) => {
              const isLocked = locked.has(eventClass)
              return (
                <tr key={eventClass} className="border-t border-navy/5">
                  <th scope="row" className="text-left py-3 pr-3 align-top">
                    <span className="block text-sm font-body font-normal text-navy">
                      {t(`profile.matrix.class.${eventClass}`)}
                    </span>
                    <span className="block text-xs font-body text-navy/40">
                      {isLocked
                        ? t('profile.matrix.alwaysOn')
                        : t(`profile.matrix.classHint.${eventClass}`)}
                    </span>
                  </th>
                  {channels.map((channel) => {
                    const on = Boolean(prefs[eventClass]?.[channel])
                    const cellKey = `${eventClass}:${channel}`
                    const label = `${t(`profile.matrix.class.${eventClass}`)} — ${t(
                      `profile.matrix.channel.${channel}`,
                    )}`
                    return (
                      <td key={channel} className="py-3 px-2 text-center">
                        <button
                          type="button"
                          onClick={() => toggle(eventClass, channel)}
                          disabled={isLocked || busy === cellKey}
                          aria-pressed={on || isLocked}
                          aria-label={label}
                          data-testid={`matrix-${eventClass}-${channel}`}
                          className={`w-10 h-6 rounded-full transition-colors disabled:opacity-50 ${
                            on || isLocked ? 'bg-cyan' : 'bg-navy/20'
                          } ${isLocked ? 'cursor-not-allowed' : ''}`}
                        >
                          <span
                            className={`block w-4 h-4 bg-white rounded-full mx-auto transition-transform ${
                              on || isLocked ? 'translate-x-2' : '-translate-x-2'
                            }`}
                          />
                        </button>
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
