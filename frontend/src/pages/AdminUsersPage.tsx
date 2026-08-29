import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { deleteUser, listAllUsers, offerRole, revokeRole } from '../api/admin'
import type { User, UserRole } from '../api/auth'
import { isSuperuser } from '../lib/permissions'
import MonoText from '../components/MonoText'

const E2E_MARKER = '@e2e.vimana.local'

/** Mirrors `core.permissions.OFFERABLE_ROLES`. `superuser` is absent: it comes
 *  from the address in the environment, not from anybody's decision. */
const OFFERABLE: UserRole[] = ['arbiter', 'compliance_editor']

export default function AdminUsersPage() {
  const { t } = useTranslation()
  const me = useAuthStore((s) => s.user)
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showTestOnly, setShowTestOnly] = useState(false)
  const [emailFilter, setEmailFilter] = useState('')
  /** Offers made during this visit, per account. Deliberately not persisted:
   *  it reports what just happened and does not claim to be the account's
   *  state. The durable answer to "who has been offered what and has not
   *  replied" is the Roles screen, which reads `/api/admin/role-offers`. */
  const [offered, setOffered] = useState<Map<string, Set<UserRole>>>(new Map())

  if (!isSuperuser(me)) return <Navigate to="/dashboard" replace />

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

  /** T3.42 — offering and revoking are no longer one toggle.
   *
   *  They stopped being symmetrical: a revocation takes effect immediately,
   *  while an offer takes effect only if the person accepts. Painting the new
   *  role onto the row after an offer — which the old toggle did — would state
   *  something the backend has not done, and the row would go back on reload.
   *  So an offer changes nothing here except a note saying it is waiting.
   */
  const failWith = (err: unknown) => {
    const detail = (err as { response?: { data?: { detail?: string } } })
      ?.response?.data?.detail
    setError(typeof detail === 'string' ? detail : t('admin.promoteError'))
  }

  const handleOffer = async (userId: string, role: UserRole) => {
    setError('')
    try {
      await offerRole(userId, role)
      setOffered((prev) => {
        const next = new Map(prev)
        next.set(userId, new Set(next.get(userId)).add(role))
        return next
      })
    } catch (err: unknown) {
      failWith(err)
    }
  }

  const handleRevoke = async (userId: string, role: UserRole) => {
    setError('')
    try {
      await revokeRole(userId, role)
      // Only this role comes off the row. Rebuilding it as `[]` would repeat
      // in the interface the exact bug the model change removed.
      setUsers((prev) =>
        prev.map((u) =>
          u.id === userId
            ? { ...u, roles: (u.roles ?? []).filter((r) => r !== role) }
            : u,
        ),
      )
      setOffered((prev) => {
        const next = new Map(prev)
        const roles = new Set(next.get(userId))
        roles.delete(role)
        roles.size ? next.set(userId, roles) : next.delete(userId)
        return next
      })
    } catch (err: unknown) {
      failWith(err)
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
              className="border border-navy/20 rounded-field px-3 py-1.5 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            />
            <button
              onClick={load}
              className="text-xs font-display font-medium border border-navy/20 text-navy px-3 py-1.5 rounded-field hover:bg-ivory"
            >
              Search
            </button>
          </>
        )}
      </div>

      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      {loading ? (
        <p className="text-sm font-body text-navy/40 text-center py-8">
          {t('common.loading')}
        </p>
      ) : (
        <div className="bg-white rounded-card border border-navy/10 overflow-hidden">
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
                        {/* T3.42 — every role held, not the one that fitted in
                            a column. Two chips side by side is the whole point
                            of the change: an account can arbitrate and edit
                            rules at the same time. */}
                        {(u.roles ?? []).map((r) => (
                          <span
                            key={r}
                            className={`text-xs font-mono px-2 py-0.5 rounded ${
                              r === 'superuser'
                                ? 'bg-navy text-ivory'
                                : 'bg-amber/20 text-amber'
                            }`}
                          >
                            {t(`roles.names.${r}`)}
                          </span>
                        ))}
                        {u.can_carry && (
                          <span className="text-xs font-mono bg-cyan/20 text-navy px-2 py-0.5 rounded">
                            carrier
                          </span>
                        )}
                        {[...(offered.get(u.id) ?? [])].map((r) => (
                          <span
                            key={`offered-${r}`}
                            className="text-xs font-mono border border-amber/50 text-amber px-2 py-0.5 rounded"
                          >
                            {t(`roles.names.${r}`)} · {t('admin.arbiterOffered')}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex gap-2">
                        {/* One button per offerable role, because they are
                            independent: offering the second must not take the
                            first away, and a single toggle cannot say that. */}
                        {u.id !== me.id &&
                          !(u.roles ?? []).includes('superuser') &&
                          OFFERABLE.map((r) => {
                            const held = (u.roles ?? []).includes(r)
                            const waiting = offered.get(u.id)?.has(r) ?? false
                            return (
                              <button
                                key={r}
                                onClick={() =>
                                  held ? handleRevoke(u.id, r) : handleOffer(u.id, r)
                                }
                                disabled={waiting && !held}
                                className={`text-xs font-display font-medium px-3 py-1 rounded-field disabled:opacity-50 ${
                                  held
                                    ? 'bg-navy/10 text-navy hover:bg-navy/20'
                                    : 'bg-amber text-white hover:opacity-90'
                                }`}
                              >
                                {held
                                  ? t('admin.revokeRole', { role: t(`roles.names.${r}`) })
                                  : t('admin.offerRole', { role: t(`roles.names.${r}`) })}
                              </button>
                            )
                          })}
                        {u.id !== me.id && !(u.roles ?? []).includes('superuser') && (
                          <button
                            onClick={() => handleDelete(u)}
                            className="text-xs font-display font-medium px-3 py-1 rounded-field bg-danger/10 text-danger hover:bg-danger/15"
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
