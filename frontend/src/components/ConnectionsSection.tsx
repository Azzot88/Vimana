import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listConnections, type Connection } from '../api/social'
import MonoText from './MonoText'

/** T_UX.20 — lifted out of `ProfilePage` unchanged, to sit next to the trust
 *  circles it belongs with: both answer "who do I already know here". */
export default function ConnectionsSection() {
  const { t, i18n } = useTranslation()
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listConnections()
      .then(({ data }) => setConnections(data))
      .catch(() => {
        // silent — an empty contact list and a failed request look the same to
        // the reader, and neither is worth an error banner on this screen.
      })
      .finally(() => setLoading(false))
  }, [])

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
                  <p className="text-sm font-body text-navy">
                    {conn.connected_user?.display_name}
                  </p>
                  <p className="text-xs font-mono text-navy/40">
                    {conn.connected_user?.active_mode === 'carrier'
                      ? t('dashboard.carrier')
                      : t('dashboard.sender')}
                  </p>
                </div>
              </div>
              <MonoText className="text-xs text-navy/30">
                {new Date(conn.created_at).toLocaleDateString(i18n.language)}
              </MonoText>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
