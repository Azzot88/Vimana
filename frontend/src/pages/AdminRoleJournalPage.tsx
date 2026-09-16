import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useParams } from 'react-router-dom'
import { roleJournal } from '../api/admin'
import type { RoleGrant } from '../api/roles'
import { isSuperuser } from '../lib/permissions'
import { usePrefs } from '../hooks/usePrefs'
import { useAuthStore } from '../stores/auth'
import MonoText from '../components/MonoText'

/**
 * T_UX.25 — where a role came from, and where it went.
 *
 * The journal has been written since T3.42 and read by nobody: `users.roles` is
 * only ever changed together with a row here, so the whole history of a role
 * existed in the database and had no screen. An arbiter's access to other
 * people's deals is exactly the kind of power whose origin somebody has to be
 * able to check.
 *
 * **A withdrawal is drawn as loudly as a grant.** Owner's point in the task: a
 * grant is remembered and a revocation is forgotten, so a journal that shows
 * only half reads as «the role was given and it is there». `revoked` gets the
 * danger colour for the same reason the row exists at all.
 *
 * Functions (PROJECT §6.2a):
 * - `AdminRoleJournalPage()` — default export. Called by: `App` at
 *   `/admin/users/:userId/roles`.
 */
const TONE: Record<RoleGrant['event'], string> = {
  offered: 'bg-amber/15 text-amber',
  accepted: 'bg-success/10 text-success',
  declined: 'bg-navy/10 text-navy/60',
  revoked: 'bg-danger/10 text-danger',
}

export default function AdminRoleJournalPage() {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const { userId } = useParams<{ userId: string }>()
  const me = useAuthStore((s) => s.user)
  const [rows, setRows] = useState<RoleGrant[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!userId) return
    const load = async () => {
      try {
        const { data } = await roleJournal(userId)
        setRows(data)
        setError('')
      } catch {
        // Not silently empty: «nothing ever happened» and «the request failed»
        // are different answers, and this page exists to be trusted.
        setRows([])
        setError(t('adminJournal.loadFailed') as string)
      }
    }
    void load()
  }, [userId, t])

  if (!isSuperuser(me)) return <Navigate to="/dashboard" replace />

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          to="/admin/users"
          className="text-xs font-body text-navy/40 hover:text-navy transition-colors"
        >
          ← {t('adminJournal.back')}
        </Link>
        <h1 className="font-display font-bold text-xl text-navy">
          {t('adminJournal.title')}
        </h1>
        <MonoText className="text-xs text-navy/40">{userId}</MonoText>
      </div>
      <p className="text-sm font-body text-navy/50">{t('adminJournal.lead')}</p>

      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      {rows === null ? (
        <p className="text-sm font-body text-navy/40 text-center py-8">
          {t('common.loading')}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm font-body text-navy/40">{t('adminJournal.empty')}</p>
      ) : (
        <div className="bg-white rounded-card border border-navy/10 overflow-x-auto">
          <table className="w-full text-sm font-body">
            <thead>
              <tr className="text-left text-xs font-display text-navy/45 uppercase tracking-wide">
                <th className="px-4 py-3">{t('adminJournal.when')}</th>
                <th className="px-4 py-3">{t('adminJournal.event')}</th>
                <th className="px-4 py-3">{t('adminJournal.role')}</th>
                <th className="px-4 py-3">{t('adminJournal.actor')}</th>
                <th className="px-4 py-3">{t('adminJournal.reason')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-navy/5 align-top">
                  <td className="px-4 py-3 whitespace-nowrap">
                    <MonoText className="text-xs text-navy/60">
                      {prefs.dateTime(row.created_at)}
                    </MonoText>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-mono font-medium ${TONE[row.event]}`}
                    >
                      {t(`adminJournal.events.${row.event}`)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-navy">
                    {t(`roles.names.${row.role}`, row.role)}
                  </td>
                  <td className="px-4 py-3 text-navy/70">
                    {/* No actor is the platform itself, and saying so is truer
                        than an empty cell. */}
                    {row.actor_name ?? t('adminJournal.platform')}
                  </td>
                  <td className="px-4 py-3 text-navy/60 whitespace-pre-wrap">
                    {row.reason || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
