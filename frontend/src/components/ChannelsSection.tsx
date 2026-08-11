import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { disconnectTelegram, getTelegramLink, me, updateMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import AddEmailModal from './AddEmailModal'

/**
 * T3.32 — the ways this account can be reached, next to the matrix that says
 * what travels down them.
 *
 * Lived on the profile until 2026-08-11. Splitting the two put a person one
 * navigation away from the answer to "why is nothing arriving in Telegram" —
 * the matrix showed a column they could not use, and the reason was on another
 * screen. Owner's decision: one page.
 *
 * **The switch *is* the connection** (T_UX.13, owner's decision 2026-08-09).
 * There is no "linked but muted" state to be in: on starts connecting, off
 * forgets the connection. Muting is what the matrix is for.
 *
 * Mail is the exception and has no switch. An account cannot un-have its
 * address, and `notify_email` stopped steering delivery when the matrix
 * arrived — a switch here would have looked like a control and done nothing.
 */
export default function ChannelsSection() {
  const { t } = useTranslation()
  const { user, token, setAuth } = useAuthStore()
  const [busyChannel, setBusyChannel] = useState<string | null>(null)
  const [emailModal, setEmailModal] = useState(false)
  const [awaitingLink, setAwaitingLink] = useState(false)

  const refreshUser = async () => {
    if (!token) return
    const { data } = await me()
    setAuth(data, token)
  }

  // T_UX.12 pt.2 — the linking happens on the server, in a webhook this tab
  // never sees. Pressing «Connect Telegram» opens Telegram, the bot answers,
  // the row is written — and this screen keeps saying «not connected» until
  // something asks again. So it asks on the way back: returning to the tab is
  // exactly the moment the answer could have changed.
  //
  // Scoped to the one pending case rather than refetching on every focus: a
  // screen that re-reads itself whenever you alt-tab is a request per glance.
  useEffect(() => {
    if (!awaitingLink || !token) return
    if (user?.telegram_chat_id) {
      setAwaitingLink(false)
      return
    }
    const recheck = () => {
      if (document.visibilityState !== 'visible') return
      me()
        .then(({ data }) => setAuth(data, token))
        .catch(() => {})
    }
    document.addEventListener('visibilitychange', recheck)
    window.addEventListener('focus', recheck)
    // Focus is the common case and the cheap one, but it is not guaranteed:
    // the desktop Telegram app can take the link without the browser ever
    // losing focus, and then no event fires at all. A bounded poll covers that
    // without becoming a background heartbeat — it exists only between the tap
    // and the answer, and gives up rather than running forever.
    const poll = setInterval(recheck, 3000)
    const stop = setTimeout(() => setAwaitingLink(false), 120_000)
    return () => {
      document.removeEventListener('visibilitychange', recheck)
      window.removeEventListener('focus', recheck)
      clearInterval(poll)
      clearTimeout(stop)
    }
  }, [awaitingLink, token, setAuth, user?.telegram_chat_id])

  const handleToggle = async (field: 'notify_whatsapp') => {
    if (!user || !token) return
    try {
      const { data } = await updateMe({ [field]: !user[field] })
      setAuth(data, token)
    } catch { /* silent */ }
  }

  const handleChannelToggle = async (key: 'notify_telegram' | 'notify_whatsapp') => {
    if (key === 'notify_telegram') {
      if (user?.telegram_chat_id) {
        setBusyChannel(key)
        try {
          await disconnectTelegram()
          await refreshUser()
        } catch { /* silent */ } finally { setBusyChannel(null) }
        return
      }
      try {
        const { data } = await getTelegramLink()
        setAwaitingLink(true)
        window.open(data.link, '_blank')
      } catch { /* silent */ }
      return
    }

    await handleToggle(key)
  }

  const rows = [
    {
      key: 'notify_email' as const,
      label: t('profile.email'),
      sub: user?.email ?? t('profile.emailAdd'),
    },
    {
      key: 'notify_telegram' as const,
      label: t('profile.telegram'),
      sub: user?.telegram_chat_id
        ? t('profile.telegramConnected')
        : t('profile.telegramWillConnect'),
    },
    {
      key: 'notify_whatsapp' as const,
      label: t('profile.whatsapp'),
      sub: user?.whatsapp_number ?? t('profile.whatsappNotSet'),
    },
  ]

  return (
    <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
      <div>
        <h2 className="font-display font-semibold text-base text-navy">
          {t('profile.channels')}
        </h2>
        <p className="text-xs font-body text-navy/50 mt-1">
          {t('profile.channelsHint')}
        </p>
      </div>

      {rows.map(({ key, label, sub }) => (
        <div key={key} className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-body text-navy">{label}</p>
            <p className="text-xs font-mono text-navy/40">{sub}</p>
          </div>
          {key === 'notify_email' ? (
            user?.email ? null : (
              <button
                type="button"
                onClick={() => setEmailModal(true)}
                data-testid="channel-email-add"
                className="text-xs font-body font-medium text-cyan hover:underline shrink-0"
              >
                {t('profile.addEmail.title')}
              </button>
            )
          ) : (
            <button
              type="button"
              onClick={() => handleChannelToggle(key)}
              disabled={busyChannel === key}
              aria-pressed={Boolean(user?.[key])}
              aria-label={label}
              data-testid={`channel-${key}`}
              className={`w-10 h-6 rounded-full transition-colors disabled:opacity-50 shrink-0 ${user?.[key] ? 'bg-cyan' : 'bg-navy/20'}`}
            >
              <span
                className={`block w-4 h-4 bg-white rounded-full mx-auto transition-transform ${user?.[key] ? 'translate-x-2' : '-translate-x-2'}`}
              />
            </button>
          )}
        </div>
      ))}

      {emailModal && (
        <AddEmailModal
          onClose={() => setEmailModal(false)}
          onDone={async () => {
            setEmailModal(false)
            await refreshUser()
          }}
        />
      )}
    </div>
  )
}
