import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { listAllUsers, promoteArbiter } from '../api/admin'
import type { User } from '../api/auth'
import MonoText from '../components/MonoText'

export default function AdminUsersPage() {
  const { t } = useTranslation()
  const me = useAuthStore((s) => s.user)
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  if (!me?.is_superuser) return <Navigate to="/dashboard" replace />

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await listAllUsers({ limit: 100 })
      setUsers(data.items)
    } catch {
      setError(t('admin.loadError'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleToggle = async (userId: string, current: boolean) => {
    setError('')
    try {
      await promoteArbiter(userId, !current)
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, is_arbiter: !current } : u)),
      )
    } catch {
      setError(t('admin.promoteError'))
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display font-bold text-2xl text-navy">
        {t('admin.usersTitle')}
      </h1>

      {error && <p className="text-xs font-mono text-red-600">{error}</p>}

      {loading ? (
        <p className="text-sm font-body text-navy/40 text-center py-8">
          {t('common.loading')}
        </p>
      ) : (
        <div className="bg-white rounded-xl border border-navy/10 overflow-hidden">
          <table className="w-full text-sm font-body">
            <thead className="bg-ivory">
              <tr className="text-left text-xs font-display font-semibold text-navy/60 uppercase tracking-wide">
                <th className="px-4 py-3">{t('admin.userCol.name')}</th>
                <th className="px-4 py-3 hidden sm:table-cell">
                  {t('admin.userCol.email')}
                </th>
                <th className="px-4 py-3">{t('admin.userCol.roles')}</th>
                <th className="px-4 py-3 text-right">
                  {t('admin.userCol.actions')}
                </th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-navy/5">
                  <td className="px-4 py-3">
                    <p className="text-navy font-medium">{u.display_name}</p>
                    <MonoText className="text-xs text-navy/40 sm:hidden">
                      {u.email ?? u.phone ?? '—'}
                    </MonoText>
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell">
                    <MonoText className="text-xs text-navy/60">
                      {u.email ?? u.phone ?? '—'}
                    </MonoText>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {u.is_superuser && (
                        <span className="text-xs font-mono bg-navy text-ivory px-2 py-0.5 rounded">
                          superuser
                        </span>
                      )}
                      {u.is_arbiter && (
                        <span className="text-xs font-mono bg-amber/20 text-amber px-2 py-0.5 rounded">
                          arbiter
                        </span>
                      )}
                      {u.is_carrier && (
                        <span className="text-xs font-mono bg-cyan/20 text-navy px-2 py-0.5 rounded">
                          carrier
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {u.id !== me.id && !u.is_superuser && (
                      <button
                        onClick={() => handleToggle(u.id, !!u.is_arbiter)}
                        className={`text-xs font-display font-medium px-3 py-1 rounded-lg ${
                          u.is_arbiter
                            ? 'bg-navy/10 text-navy hover:bg-navy/20'
                            : 'bg-amber text-white hover:opacity-90'
                        }`}
                      >
                        {u.is_arbiter
                          ? t('admin.revokeArbiter')
                          : t('admin.makeArbiter')}
                      </button>
                    )}
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
