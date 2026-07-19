import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listPlatformNotices, type PlatformNotice } from '../api/notices'

const SEVERITY_CLASS: Record<PlatformNotice['severity'], string> = {
  info: 'bg-cyan/10 border-cyan/30 text-navy',
  warning: 'bg-amber/10 border-amber/40 text-navy',
  alert: 'bg-red-50 border-red-300 text-red-800',
}

interface Props {
  surface?: PlatformNotice['target_surface']
}

/** T_UX.2 pt.2 — surface-scoped rendering of active platform notices.
 *  Uses `t(notice.key, notice.key)` — if translation is missing, the key
 *  itself is shown as fallback (superuser can write human-readable keys). */
export default function PlatformNoticeBanner({ surface = 'all' }: Props) {
  const { t } = useTranslation()
  const [notices, setNotices] = useState<PlatformNotice[]>([])

  useEffect(() => {
    listPlatformNotices({ surface })
      .then(({ data }) => setNotices(data))
      .catch(() => setNotices([]))
  }, [surface])

  if (notices.length === 0) return null

  return (
    <div className="space-y-2">
      {notices.map((n) => (
        <div
          key={n.id}
          className={`border rounded-lg px-3 py-2 text-sm font-body ${SEVERITY_CLASS[n.severity]}`}
        >
          {t(n.key, n.key)}
        </div>
      ))}
    </div>
  )
}
