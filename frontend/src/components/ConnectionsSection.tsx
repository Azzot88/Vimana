import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  acceptClose,
  declineClose,
  endClose,
  listClose,
  listConnections,
  removeConnection,
  requestClose,
  type ClosePair,
  type Connection,
} from '../api/social'
import MonoText from './MonoText'

/** T_UX.20 — lifted out of `ProfilePage` unchanged, to sit next to the trust
 *  circles it belongs with: both answer "who do I already know here".
 *
 *  T3.12.06 — contacts and close people, and closeness is **asked and
 *  accepted** (owner, 2026-09-14). A contact row offers to ask; a request made
 *  of me stands above the list with its answer, because the person asking need
 *  not be in my contacts; and «ждём ответа» is its own visible state, since an
 *  unanswered request has not made anybody close. Close people see the whole
 *  profile, addresses included — that part is `T3.12.06 pt.2`.
 */
export default function ConnectionsSection() {
  const { t, i18n } = useTranslation()
  const [connections, setConnections] = useState<Connection[]>([])
  const [requests, setRequests] = useState<ClosePair[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)

  const reload = () =>
    Promise.all([
      listConnections().then(({ data }) => setConnections(data)),
      listClose().then(({ data }) =>
        setRequests(data.filter((p) => p.state === 'close_requested')),
      ),
    ]).catch(() => {
      // silent — an empty contact list and a failed request look the same to
      // the reader, and neither is worth an error banner on this screen.
    })

  useEffect(() => {
    reload().finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** The whole list is re-read after a change rather than one row patched in
   *  place: closeness is a fact about a *pair*, and the server is the only thing
   *  that knows whether the other half answered. */
  const change = async (key: string, act: () => Promise<unknown>) => {
    setBusy(key)
    try {
      await act()
      await reload()
    } finally {
      setBusy(null)
    }
  }

  const closeAction = (conn: Connection) => {
    const userId = conn.connected_user_id
    switch (conn.state) {
      case 'close':
        return { label: t('contacts.stepBack'), act: () => endClose(userId) }
      case 'close_pending':
        return { label: t('contacts.cancelRequest'), act: () => endClose(userId) }
      case 'close_requested':
        // Answered in the block above, where the request is.
        return null
      default:
        return { label: t('contacts.makeClose'), act: () => requestClose(userId) }
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

      {requests.length > 0 && (
        <div className="space-y-2 rounded-field border border-cyan/30 bg-cyan/5 p-3">
          <p className="text-xs font-body font-medium text-navy/60">
            {t('contacts.incomingTitle')}
          </p>
          {requests.map((pair) => (
            <div
              key={pair.id}
              data-testid="close-request"
              className="flex items-center justify-between gap-3"
            >
              <span className="text-sm font-body text-navy truncate">
                {pair.display_name}
              </span>
              <div className="flex items-center gap-3 shrink-0">
                <button
                  type="button"
                  disabled={busy === pair.id}
                  onClick={() => change(pair.id, () => acceptClose(pair.id))}
                  className="text-xs font-body text-cyan hover:underline disabled:opacity-40"
                >
                  {t('contacts.closeAccept')}
                </button>
                <button
                  type="button"
                  disabled={busy === pair.id}
                  onClick={() => change(pair.id, () => declineClose(pair.id))}
                  className="text-xs font-body text-navy/40 hover:text-amber disabled:opacity-40"
                >
                  {t('contacts.closeDecline')}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
      ) : connections.length === 0 ? (
        <p className="text-sm font-body text-navy/40">{t('profile.noContacts')}</p>
      ) : (
        <div className="space-y-2">
          {connections.map((conn) => {
            const action = closeAction(conn)
            return (
              <div
                key={conn.id}
                className="flex items-center justify-between py-2 border-b border-navy/5 last:border-0"
              >
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-ivory border border-navy/10 flex items-center justify-center">
                    <span className="text-xs font-display font-bold text-navy">
                      {/* Optional chaining on the field, not only on the index.
                          `undefined[0]` throws; `""[0]` does not. */}
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
                      {conn.state === 'close_requested' && (
                        <span className="text-[10px] font-mono uppercase bg-cyan/10 text-cyan px-1.5 py-0.5 rounded">
                          {t('contacts.requested')}
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
                  {action && (
                    <button
                      type="button"
                      disabled={busy === conn.connected_user_id}
                      onClick={() => change(conn.connected_user_id, action.act)}
                      className="text-xs font-body text-cyan hover:underline disabled:opacity-40"
                    >
                      {action.label}
                    </button>
                  )}
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
            )
          })}
        </div>
      )}
    </div>
  )
}
