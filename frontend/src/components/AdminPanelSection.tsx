import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getScanQueue, type ScanQueue } from '../api/admin'
import { useAuthStore } from '../stores/auth'
import { hasRole, isStaff, isSuperuser } from '../lib/permissions'
import type { UserRole } from '../api/auth'
import MonoText from './MonoText'

interface AdminLink {
  to: string
  labelKey: string
  descKey: string
  roles: UserRole[]
  icon: string
}

const LINKS: AdminLink[] = [
  {
    to: '/admin/disputes',
    labelKey: 'admin.disputes',
    descKey: 'admin.disputesDesc',
    roles: ['arbiter', 'superuser'],
    icon: '⚖',
  },
  {
    to: '/admin/users',
    labelKey: 'admin.users',
    descKey: 'admin.usersDesc',
    roles: ['superuser'],
    icon: '👥',
  },
  {
    // T3.42 — next to Users on purpose: it answers the question that screen
    // raises and cannot answer, namely which of those offers is still waiting.
    to: '/admin/role-offers',
    labelKey: 'admin.roles',
    descKey: 'admin.rolesDesc',
    roles: ['superuser'],
    icon: '🎫',
  },
  {
    // T3.11.02 — the only entry an editor without superuser can reach, which is
    // why the role list here is not `['superuser']`.
    to: '/admin/rules',
    labelKey: 'admin.rules',
    descKey: 'admin.rulesDesc',
    roles: ['compliance_editor', 'superuser'],
    icon: '📋',
  },
  {
    to: '/admin/notices',
    labelKey: 'admin.notices',
    descKey: 'admin.noticesDesc',
    roles: ['superuser'],
    icon: '📢',
  },
  {
    to: '/admin/email',
    labelKey: 'admin.email',
    descKey: 'admin.emailDesc',
    roles: ['superuser'],
    icon: '✉',
  },
  {
    to: '/admin/params',
    labelKey: 'admin.params',
    descKey: 'admin.paramsDesc',
    roles: ['superuser'],
    icon: '⚙',
  },
]

/** T_UX.2 pt.3 follow-up — surface all admin routes in the personal cabinet
 *  so nothing is reachable only via URL. Role-gated per route. */
export default function AdminPanelSection() {
  const { user } = useAuthStore()
  const { t } = useTranslation()
  const [queue, setQueue] = useState<ScanQueue | null>(null)

  // T3.42 — roles add up, so a link is visible when the account holds **any**
  // of the roles it names. The old `.includes(role)` asked whether one string
  // was in the link's list, which stops being a question once a person can
  // hold two.
  const isSuper = isSuperuser(user)


  // T3.8 — only the superuser. `scan-queue` is behind `USERS_MANAGE`, so
  // asking as an arbiter would spend a request to be told 403.
  useEffect(() => {
    if (!isSuper) return
    getScanQueue()
      .then(({ data }) => setQueue(data))
      .catch(() => {})
  }, [isSuper])

  // T3.11.02 — staff, not arbiters: a rules editor is neither an arbiter nor a
  // superuser, and the link list below already says who sees what.
  if (!isStaff(user)) return null

  const visible = LINKS.filter((l) => l.roles.some((r) => hasRole(user, r)))
  if (visible.length === 0) return null

  return (
    <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
      <div>
        <h2 className="font-display font-semibold text-base text-navy">
          {t('admin.panelTitle')}
        </h2>
        <p className="text-xs font-body text-navy/40 mt-0.5">{t('admin.panelHint')}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {visible.map((l) => (
          <Link
            key={l.to}
            to={l.to}
            className="flex items-start gap-3 p-3 rounded-field border border-navy/10 hover:border-cyan hover:bg-cyan/5 transition-colors"
          >
            <span className="text-xl leading-none">{l.icon}</span>
            <div className="min-w-0">
              <p className="font-display font-medium text-sm text-navy">
                {t(l.labelKey)}
              </p>
              <p className="text-xs font-body text-navy/50 leading-snug">
                {t(l.descKey)}
              </p>
            </div>
          </Link>
        ))}
      </div>

      {/* T3.8 — the scan queue as a state, not an alert.
          The Telegram message is a moment: it arrives, and if nobody is at the
          keyboard it is gone. This number is still here tomorrow, and a queue
          that keeps climbing says more than any single outage did. */}
      {queue && (
        <div
          data-testid="scan-queue"
          className="rounded-field border border-navy/10 bg-ivory p-4 space-y-2"
        >
          <div className="flex items-baseline justify-between gap-3">
            <p className="font-display font-medium text-sm text-navy">
              {t('admin.scanQueue.title')}
            </p>
            {!queue.scanner_configured && (
              <MonoText className="text-[11px] text-amber">
                {t('admin.scanQueue.noScanner')}
              </MonoText>
            )}
          </div>
          <dl className="flex flex-wrap gap-x-6 gap-y-1">
            {([
              ['pending', queue.pending],
              ['clean', queue.clean],
              ['infected', queue.infected],
            ] as const).map(([key, value]) => (
              <div key={key} className="flex items-baseline gap-2">
                <dt className="text-xs font-body text-navy/50">
                  {t(`admin.scanQueue.${key}`)}
                </dt>
                <dd>
                  <MonoText
                    className={`text-sm ${
                      key === 'infected' && value > 0 ? 'text-danger' : 'text-navy'
                    }`}
                  >
                    {value}
                  </MonoText>
                </dd>
              </div>
            ))}
          </dl>
          {/* Said every time the number is shown, because the number invites
              exactly the wrong reading: pending files are not "being checked",
              they are stored and downloadable while nobody has looked. */}
          <p className="text-[11px] font-body text-navy/45 leading-snug">
            {t('admin.scanQueue.hint')}
          </p>
        </div>
      )}
    </div>
  )
}
