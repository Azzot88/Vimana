import { useEffect, useState } from 'react'
import { listPlatformNotices, type PlatformNotice } from '../api/notices'

const SEVERITY_CLASS: Record<PlatformNotice['severity'], string> = {
  info: 'bg-cyan/10 border-cyan/30 text-navy',
  warning: 'bg-amber/10 border-amber/40 text-navy',
  alert: 'bg-danger/5 border-danger/30 text-danger',
}

interface Props {
  surface?: PlatformNotice['target_surface']
}

/** T_UX.2 pt.4 — renders active platform notices with direct text
 *  (headline + optional body). No i18n key resolution — content is the
 *  content the superuser wrote. */
export default function PlatformNoticeBanner({ surface = 'all' }: Props) {
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
          className={`border rounded-field px-3 py-2 text-sm font-body ${SEVERITY_CLASS[n.severity]}`}
        >
          <p className="font-medium">{n.headline || n.key}</p>
          {n.body && <p className="text-xs mt-1 whitespace-pre-line opacity-80">{n.body}</p>}
        </div>
      ))}
    </div>
  )
}
