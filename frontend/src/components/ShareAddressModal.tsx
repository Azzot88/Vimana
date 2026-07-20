import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listAddresses, type Address } from '../api/addresses'
import MonoText from './MonoText'

interface Props {
  open: boolean
  onClose: () => void
  onShare: (addressId: string) => Promise<void>
}

/** T_UX.4 C — picker used in DealVault + Inquiry chats. Lists the user's
 *  saved addresses, defaults selection to the flagged one, and delegates
 *  the actual POST to the parent (parent owns the message state). */
export default function ShareAddressModal({ open, onClose, onShare }: Props) {
  const { t } = useTranslation()
  const [addresses, setAddresses] = useState<Address[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError('')
    listAddresses()
      .then(({ data }) => {
        setAddresses(data)
        const def = data.find((a) => a.is_default) ?? data[0]
        setSelected(def?.id ?? null)
      })
      .catch(() => setError(t('common.errorGeneric') as string))
      .finally(() => setLoading(false))
  }, [open, t])

  if (!open) return null

  const handleShare = async () => {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      await onShare(selected)
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('chat.shareAddress.error') as string)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl max-h-[90vh] overflow-y-auto"
      >
        <h3 className="font-display font-semibold text-lg text-navy">
          {t('address.pickerTitle')}
        </h3>

        {loading ? (
          <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
        ) : addresses.length === 0 ? (
          <p className="text-sm font-body text-navy/60">
            {t('address.empty')}
          </p>
        ) : (
          <div className="space-y-2">
            {addresses.map((a) => (
              <label
                key={a.id}
                className={`flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                  selected === a.id
                    ? 'border-cyan bg-cyan/5'
                    : 'border-navy/10 hover:border-navy/30'
                }`}
              >
                <input
                  type="radio"
                  name="address"
                  value={a.id}
                  checked={selected === a.id}
                  onChange={() => setSelected(a.id)}
                  className="mt-1 accent-cyan"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <p className="font-display font-medium text-sm text-navy">
                      {a.label}
                    </p>
                    {a.is_default && (
                      <span className="text-[10px] font-mono uppercase bg-cyan/15 text-cyan px-1.5 py-0.5 rounded">
                        {t('address.default')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-body text-navy/60">
                    {[a.country_iso, a.city, a.street, a.postal_code]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                  {a.note && (
                    <p className="text-xs font-mono text-navy/40 mt-0.5">{a.note}</p>
                  )}
                </div>
              </label>
            ))}
          </div>
        )}

        {error && <p className="text-xs font-mono text-red-600">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="text-sm font-body text-navy/60 hover:text-navy px-4 py-2"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={handleShare}
            disabled={busy || !selected || addresses.length === 0}
            className="bg-navy text-ivory font-display font-medium text-sm px-5 py-2 rounded-lg hover:bg-navy-mid disabled:opacity-50"
          >
            {busy ? t('common.sending') : t('chat.shareAddress.button')}
          </button>
        </div>
      </div>
    </div>
  )
}
