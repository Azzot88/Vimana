import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { deleteUser, listAllUsers, promoteArbiter } from '../api/admin'
import type { User } from '../api/auth'
import MonoText from '../components/MonoText'

const E2E_MARKER = '@e2e.vimana.local'

export default function AdminUsersPage() {
  const { t } = useTranslation()
  const me = useAuthStore((s) => s.user)
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showTestOnly, setShowTestOnly] = useState(false)
  const [emailFilter, setEmailFilter] = useState('')

  if (me?.role !== 'superuser') return <Navigate to="/dashboard" replace />

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await listAllUsers({
        limit: 100,
        email_contains: showTestOnly ? E2E_MARKER : emailFilter || undefined,
      })
      setUsers(data.items)
    } catch {
      setError(t('admin.loadError'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [showTestOnly])

  const handleToggle = async (userId: string, current: boolean) => {
    setError('')
    try {
      await promoteArbiter(userId, !current)
      setUsers((prev) =>
        prev.map((u) =>
          u.id === userId ? { ...u, role: current ? 'user' : 'arbiter' } : u,
        ),
      )
    } catch {
      setError(t('admin.promoteError'))
    }
  }

  const handleDelete = async (user: User) => {
    const isTestUser = (user.email ?? '').endsWith(E2E_MARKER)
    const confirmMsg = isTestUser
      ? `Delete test user ${user.email}? Cascade removes trips/deals/messages.`
      : `Delete user ${user.email ?? user.phone ?? user.id}? This is a hard delete with cascade — cannot be undone.`
    if (!confirm(confirmMsg)) return
    setError('')
    try {
      await deleteUser(user.id)
      setUsers((prev) => prev.filter((u) => u.id !== user.id))
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail
      setError(typeof detail === 'string' ? detail : 'Delete failed')
    }
  }

  const testCount = useMemo(
    () => users.filter((u) => (u.email ?? '').endsWith(E2E_MARKER)).length,
    [users],
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display font-bold text-2xl text-navy">
          {t('admin.usersTitle')}
        </h1>
        <MonoText className="text-xs text-navy/50">
          {users.length} total {testCount > 0 && `· ${testCount} test`}
        </MonoText>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs font-body text-navy/70 cursor-pointer">
          <input
            type="checkbox"
            checked={showTestOnly}
            onChange={(e) => setShowTestOnly(e.target.checked)}
          />
          Only e2e test users ({E2E_MARKER})
        </label>
        {!showTestOnly && (
          <>
            <input
              type="text"
              value={emailFilter}
              onChange={(e) => setEmailFilter(e.target.value)}
              placeholder="Filter by email substring…"
              className="border border-navy/20 rounded-lg px-3 py-1.5 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            />
            <button
              onClick={load}
              className="text-xs font-display font-medium border border-navy/20 text-navy px-3 py-1.5 rounded-lg hover:bg-ivory"
            >
              Search
            </button>
          </>
        )}
      </div>

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
              {users.map((u) => {
                const isTest = (u.email ?? '').endsWith(E2E_MARKER)
                return (
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
                        {isTest && (
                          <span className="text-xs font-mono bg-amber/20 text-amber px-2 py-0.5 rounded">
                            test
                          </span>
                        )}
                        {u.role === 'superuser' && (
                          <span className="text-xs font-mono bg-navy text-ivory px-2 py-0.5 rounded">
                            superuser
                          </span>
                        )}
                        {u.role === 'arbiter' && (
                          <span className="text-xs font-mono bg-amber/20 text-amber px-2 py-0.5 rounded">
                            arbiter
                          </span>
                        )}
                        {u.can_carry && (
                          <span className="text-xs font-mono bg-cyan/20 text-navy px-2 py-0.5 rounded">
                            carrier
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex gap-2">
                        {u.id !== me.id && u.role !== 'superuser' && (
                          <button
                            onClick={() =>
                              handleToggle(u.id, u.role === 'arbiter')
                            }
                            className={`text-xs font-display font-medium px-3 py-1 rounded-lg ${
                              u.role === 'arbiter'
                                ? 'bg-navy/10 text-navy hover:bg-navy/20'
                                : 'bg-amber text-white hover:opacity-90'
                            }`}
                          >
                            {u.role === 'arbiter'
                              ? t('admin.revokeArbiter')
                              : t('admin.makeArbiter')}
                          </button>
                        )}
                        {u.id !== me.id && u.role !== 'superuser' && (
                          <button
                            onClick={() => handleDelete(u)}
                            className="text-xs font-display font-medium px-3 py-1 rounded-lg bg-red-100 text-red-700 hover:bg-red-200"
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
