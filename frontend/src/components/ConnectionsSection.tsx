import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  listConnections,
  removeConnection,
  setConnectionTier,
  type Connection,
} from '../api/social'
import MonoText from './MonoText'

/** T_UX.20 — lifted out of `ProfilePage` unchanged, to sit next to the trust
 *  circles it belongs with: both answer "who do I already know here".
 *
 *  T3.11.24 — and now what each of them is. Two tiers, and the difference
 *  between them is not decoration: close contacts are meant to see the whole
 *  profile, addresses included. So the row shows `state`, not `tier` — what is
 *  true of the pair rather than what I declared — and «ждём ответа» is its own
 *  visible state, because a request the other side has not answered has not
 *  made anybody close.
 */
export default function ConnectionsSection() {
  const { t, i18n } = useTranslation()
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)

  const reload = () =>
    listConnections()
      .then(({ data }) => setConnections(data))
      .catch(() => {
        // silent — an empty contact list and a failed request look the same to
        // the reader, and neither is worth an error banner on this screen.
      })

  useEffect(() => {
    reload().finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** T3.11.24 — the whole list is re-read after a change rather than the one
   *  row patched in place: closeness is a fact about a *pair*, and the row the
   *  server sends back is the only thing that knows whether the other half
   *  agreed. Patching locally would have printed my declaration as the answer. */
  const change = async (userId: string, act: () => Promise<unknown>) => {
    setBusy(userId)
    try {
      await act()
      await reload()
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4 h-full">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display font-semibold text-base text-navy">
            {t('profile.contacts')}
          </h2>
          {/* T_UX.22 — a line under every heading (DESIGNGUIDELINES §9b). */}
          <p className="text-xs font-body text-navy/50 mt-0.5">{t('profile.contactsDesc')}</p>
        </div>
        <Link to="/invite" className="text-xs font-body text-cyan hover:underline shrink-0">
          {t('profile.invite')}
        </Link>
      </div>
      {loading ? (
        <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
      ) : connections.length === 0 ? (
        <p className="text-sm font-body text-navy/40">{t('profile.noContacts')}</p>
      ) : (
        <div className="space-y-2">
          {connections.map((conn) => (
            <div
              key={conn.id}
              className="flex items-center justify-between py-2 border-b border-navy/5 last:border-0"
            >
              <div className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-full bg-ivory border border-navy/10 flex items-center justify-center">
                  <span className="text-xs font-display font-bold text-navy">
                    {/* Optional chaining on the field, not only on the index.
                        `undefined[0]` throws; `""[0]` does not, which is
                        exactly why the old line looked safe. */}
                    {conn.connected_user?.display_name?.[0]?.toUpperCase()}
                  </span>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-body text-navy">
                      {conn.connected_user?.display_name}
                    </p>
                    {conn.state === 'close' && (
                      <span className="text-[10px] font-mono uppercase bg-cyan/15 text-cyan px-1.5 py-0.5 rounded">
                        {t('contacts.close')}
                      </span>
                    )}
                    {conn.state === 'close_pending' && (
                      <span className="text-[10px] font-mono uppercase bg-navy/5 text-navy/50 px-1.5 py-0.5 rounded">
                        {t('contacts.closePending')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-mono text-navy/40">
                    {conn.connected_user?.active_mode === 'carrier'
                      ? t('dashboard.carrier')
                      : t('dashboard.sender')}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <button
                  type="button"
                  disabled={busy === conn.connected_user_id}
                  onClick={() =>
                    change(conn.connected_user_id, () =>
                      setConnectionTier(
                        conn.connected_user_id,
                        conn.tier === 'close' ? 'connection' : 'close',
                      ),
                    )
                  }
                  className="text-xs font-body text-cyan hover:underline disabled:opacity-40"
                >
                  {conn.tier === 'close'
                    ? t('contacts.stepBack')
                    : t('contacts.makeClose')}
                </button>
                <button
                  type="button"
                  disabled={busy === conn.connected_user_id}
                  onClick={() =>
                    change(conn.connected_user_id, () =>
                      removeConnection(conn.connected_user_id),
                    )
                  }
                  className="text-xs font-body text-navy/40 hover:text-amber disabled:opacity-40"
                >
                  {t('contacts.remove')}
                </button>
                <MonoText className="text-xs text-navy/30 hidden sm:block">
                  {new Date(conn.created_at).toLocaleDateString(i18n.language)}
                </MonoText>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
