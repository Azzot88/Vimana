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
 *  exist are decisions with one home in `core/notification_prefs`. A list
 *  hardcoded here would be a second copy free to drift — and drift here means
 *  offering somebody a switch for a message that never arrives.
 *
 *  **Checkboxes, not switches** (owner's decision 2026-08-11). A switch is a
 *  power control and belongs to the channel itself, above; twelve of them in a
 *  grid read as twelve devices rather than as one set of choices. A checkbox is
 *  what a cell in a table is.
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
  const reachable = user?.notification_channels ?? {}
  const classes = Object.keys(prefs)
  // Every row carries the same channels — the server fills the matrix in full,
  // so the first row is a safe place to read the column order from.
  const channels = Object.keys(prefs[classes[0]] ?? {})

  // Nothing to draw before /me answers. An empty table with headers reads as
  // broken.
  if (!classes.length || !channels.length) return null

  /** One cell, one request. The backend merges rather than assigns, so a click
   *  cannot disturb a row this screen is not even showing. */
  const toggle = async (eventClass: string, channel: string) => {
    if (!token || locked.has(eventClass) || !reachable[channel]) return
    const cellKey = `${eventClass}:${channel}`
    setBusy(cellKey)
    try {
      const { data } = await updateMe({
        notification_prefs: { [eventClass]: { [channel]: !prefs[eventClass][channel] } },
      })
      setAuth(data, token)
    } catch {
      // Silent, and the cell snaps back on the next read: the checkbox reflects
      // what the server stored, never what was clicked.
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
      <div>
        <h2 className="font-display font-semibold text-base text-navy">
          {t('profile.matrix.title')}
        </h2>
        <p className="text-xs font-body text-navy/50 mt-1">
          {t('profile.matrix.hint')}
        </p>
      </div>

      {/* Scrolls inside itself rather than pushing the page sideways — three
          channels plus a label column is already wide on a phone. */}
      <div className="overflow-x-auto -mx-2 px-2">
        <table className="w-full min-w-[22rem] border-collapse">
          <thead>
            <tr>
              <th className="text-left pb-2" />
              {channels.map((channel) => {
                const connected = Boolean(reachable[channel])
                return (
                  <th
                    key={channel}
                    scope="col"
                    className="pb-2 px-2 text-center whitespace-nowrap align-bottom"
                  >
                    <span
                      className={`block text-xs font-body font-medium ${connected ? 'text-navy/60' : 'text-navy/30'}`}
                    >
                      {t(`profile.matrix.channel.${channel}`)}
                    </span>
                    {/* The reason lives in the header, once, rather than in
                        every cell below it: the column is unusable as a whole,
                        and repeating that four times is noise. */}
                    {!connected && (
                      <span className="block text-[10px] font-body text-navy/30">
                        {t('profile.matrix.notConnected')}
                      </span>
                    )}
                  </th>
                )
              })}
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
                    const connected = Boolean(reachable[channel])
                    const on = Boolean(prefs[eventClass]?.[channel])
                    const cellKey = `${eventClass}:${channel}`
                    const label = `${t(`profile.matrix.class.${eventClass}`)} — ${t(
                      `profile.matrix.channel.${channel}`,
                    )}`
                    return (
                      <td key={channel} className="py-3 px-2 text-center">
                        <input
                          type="checkbox"
                          // A locked class is checked whatever is stored: the
                          // letters go out regardless, and an unchecked box
                          // next to «always on» would contradict its own label.
                          checked={(on || isLocked) && connected}
                          disabled={isLocked || !connected || busy === cellKey}
                          onChange={() => toggle(eventClass, channel)}
                          aria-label={label}
                          data-testid={`matrix-${eventClass}-${channel}`}
                          className="w-4 h-4 accent-cyan align-middle disabled:opacity-40 disabled:cursor-not-allowed"
                        />
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
