import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'

interface AdminLink {
  to: string
  labelKey: string
  descKey: string
  roles: Array<'arbiter' | 'superuser'>
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
    to: '/admin/notices',
    labelKey: 'admin.notices',
    descKey: 'admin.noticesDesc',
    roles: ['superuser'],
    icon: '📢',
  },
]

/** T_UX.2 pt.3 follow-up — surface all admin routes in the personal cabinet
 *  so nothing is reachable only via URL. Role-gated per route. */
export default function AdminPanelSection() {
  const { user } = useAuthStore()
  const { t } = useTranslation()

  const role = user?.role
  if (role !== 'arbiter' && role !== 'superuser') return null

  const visible = LINKS.filter((l) => l.roles.includes(role))
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
    </div>
  )
}
