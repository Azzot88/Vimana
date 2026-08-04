import { useState } from 'react'
import { useTranslation } from 'react-i18next'

interface Props {
  eventId: string | null | undefined
  publishedAt?: string | null
}

/** T3.5 — small "📡 Also on Nostr" chip on trip cards.
 *  Renders nothing if the trip hasn't been published yet.
 *  Click copies the Nostr event id to clipboard. */
export default function NostrBadge({ eventId, publishedAt }: Props) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  if (!eventId) return null

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(eventId)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // ignore
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={publishedAt ? new Date(publishedAt).toLocaleString() : ''}
      className="inline-flex items-center gap-1 text-xs font-mono bg-cyan/10 text-cyan px-1.5 py-0.5 rounded hover:bg-cyan/20 transition-colors"
    >
      <span>📡</span>
      <span>{copied ? t('common.copied') : t('trips.alsoOnNostr')}</span>
    </button>
  )
}
