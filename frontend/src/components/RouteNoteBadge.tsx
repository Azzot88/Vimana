import { useState } from 'react'
import type { RouteNote } from '../api/notices'

const STATUS_CLASS: Record<RouteNote['status'], string> = {
  standard: '',
  attention: 'bg-cyan/15 text-link border-cyan/30',
  complex: 'bg-amber/20 text-amber border-amber/40',
  restricted: 'bg-danger/10 text-danger border-danger/30',
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

/** T_UX.2 pt.4 — RouteNote pill with expandable body. Renders headline/body
 *  directly (edited by the platform owner via /admin/notices). No i18n key
 *  resolution — content is what the superuser typed. */
export default function RouteNoteBadge({ note, compact = false }: Props) {
  const [expanded, setExpanded] = useState(false)

  if (note.status === 'standard') return null

  const headline = note.headline || `${note.origin_iso}→${note.destination_iso}`

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
        {!compact && <span className="ml-1">{headline}</span>}
      </button>
      {expanded && (
        <div className={`mt-1 max-w-md text-xs font-body p-2 rounded border ${STATUS_CLASS[note.status]}`}>
          <p className="font-medium mb-1">{headline}</p>
          {note.body && <p className="text-muted whitespace-pre-line">{note.body}</p>}
        </div>
      )}
    </div>
  )
}
