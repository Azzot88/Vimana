import { useState } from 'react'
import { useTranslation } from 'react-i18next'

const PREFIX = '📍 SHARED ADDRESS'

interface ParsedAddress {
  country?: string
  city?: string
  street?: string
  postal?: string
  note?: string
}

export function isAddressMessage(text: string | null | undefined): boolean {
  return !!text && text.startsWith(PREFIX)
}

function parseAddress(text: string): ParsedAddress {
  const parsed: ParsedAddress = {}
  const lines = text.split('\n').slice(1)
  for (const line of lines) {
    const colon = line.indexOf(':')
    if (colon < 0) continue
    const key = line.slice(0, colon).trim().toLowerCase()
    const val = line.slice(colon + 1).trim()
    if (key === 'country') parsed.country = val
    else if (key === 'city') parsed.city = val
    else if (key === 'street') parsed.street = val
    else if (key === 'postal') parsed.postal = val
    else if (key === 'note') parsed.note = val
  }
  return parsed
}

function buildMapsUrl(a: ParsedAddress): string {
  const parts = [a.street, a.city, a.country, a.postal].filter(Boolean).join(', ')
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(parts)}`
}

function buildFullText(a: ParsedAddress): string {
  return [a.street, a.city, a.postal, a.country].filter(Boolean).join(', ')
}

export default function AddressCard({ text }: { text: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const addr = parseAddress(text)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(buildFullText(addr))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // ignored
    }
  }

  return (
    <div className="border border-cyan/30 bg-cyan/5 rounded-xl p-3 max-w-md space-y-1">
      <p className="text-xs font-display font-semibold text-cyan uppercase tracking-wide">
        📍 {t('chat.addressCard.title')}
      </p>
      <dl className="text-sm font-body text-navy grid grid-cols-[auto,1fr] gap-x-2 gap-y-0.5">
        {addr.country && (
          <>
            <dt className="text-navy/40">{t('chat.addressCard.country')}:</dt>
            <dd>{addr.country}</dd>
          </>
        )}
        {addr.city && (
          <>
            <dt className="text-navy/40">{t('chat.addressCard.city')}:</dt>
            <dd>{addr.city}</dd>
          </>
        )}
        {addr.street && (
          <>
            <dt className="text-navy/40">{t('chat.addressCard.street')}:</dt>
            <dd>{addr.street}</dd>
          </>
        )}
        {addr.postal && (
          <>
            <dt className="text-navy/40">{t('chat.addressCard.postal')}:</dt>
            <dd className="font-mono text-xs">{addr.postal}</dd>
          </>
        )}
        {addr.note && (
          <>
            <dt className="text-navy/40">{t('chat.addressCard.note')}:</dt>
            <dd className="text-navy/70 italic">{addr.note}</dd>
          </>
        )}
      </dl>
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={handleCopy}
          className="text-xs font-body text-cyan hover:underline"
        >
          {copied ? t('chat.addressCard.copied') : t('chat.addressCard.copy')}
        </button>
        <a
          href={buildMapsUrl(addr)}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-body text-cyan hover:underline"
        >
          {t('chat.addressCard.openMaps')}
        </a>
      </div>
    </div>
  )
}
