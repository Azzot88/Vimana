import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { RouteNote } from '../api/notices'

const STATUS_CLASS: Record<RouteNote['status'], string> = {
  standard: '',
  attention: 'bg-cyan/15 text-cyan border-cyan/30',
  complex: 'bg-amber/20 text-amber border-amber/40',
  restricted: 'bg-red-100 text-red-700 border-red-300',
}

const STATUS_ICON: Record<RouteNote['status'], string> = {
  standard: '',
  attention: 'ⓘ',
  complex: '⚠',
  restricted: '⛔',
}

interface Props {
  note: RouteNote
  compact?: boolean
}

/** T_UX.2 pt.3 — RouteNote pill, expandable on click.
 *  `t(note.headline_i18n_key, note.headline_i18n_key)` — fallback показывает
 *  сам ключ (superuser пишет human-readable keys как MVP). */
export default function RouteNoteBadge({ note, compact = false }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  if (note.status === 'standard') return null

  return (
    <div className="inline-block">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className={`inline-flex items-center gap-1 text-xs font-body border rounded px-1.5 py-0.5 hover:opacity-80 ${STATUS_CLASS[note.status]}`}
      >
        <span>{STATUS_ICON[note.status]}</span>
        <span className="font-mono">
          {note.origin_iso === '*' ? '∗' : note.origin_iso}→
          {note.destination_iso === '*' ? '∗' : note.destination_iso}
        </span>
        {!compact && (
          <span className="ml-1">
            {t(note.headline_i18n_key, note.headline_i18n_key)}
          </span>
        )}
      </button>
      {expanded && (
        <div className={`mt-1 max-w-md text-xs font-body p-2 rounded border ${STATUS_CLASS[note.status]}`}>
          <p className="font-medium mb-1">
            {t(note.headline_i18n_key, note.headline_i18n_key)}
          </p>
          <p className="text-navy/70">
            {t(note.body_i18n_key, note.body_i18n_key)}
          </p>
        </div>
      )}
    </div>
  )
}
