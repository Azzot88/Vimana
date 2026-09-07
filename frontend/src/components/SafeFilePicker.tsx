import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listMyFiles, type SafeFile } from '../api/dealvault'
import { usePrefs } from '../hooks/usePrefs'
import MonoText from './MonoText'

interface Props {
  open: boolean
  onClose: () => void
  onPick: (fileId: string) => Promise<void>
}

/** T3.11.25 — the files this account already has, offered to the deal at hand.
 *
 *  Owner's statement 2026-09-07: «файлы из одной сделки с этим аккаунтом
 *  доступны и для новых сделок и уже там должны присутствовать». Before this,
 *  the passport sent for one parcel lived inside that deal and nowhere else,
 *  so the next one meant finding the file again and uploading it again.
 *
 *  Every row carries **«впервые предоставлен»**, because that is the fact the
 *  feature turns on: attaching an old document here does not claim it was
 *  provided for this parcel, and the date is how a reader tells the two apart.
 *  The list is deliberately plain — a document is chosen by what it is and when
 *  it first arrived, not by a thumbnail.
 *
 *  Functions (PROJECT §6.2a):
 *  - `SafeFilePicker({ open, onClose, onPick })` — default export. Called by:
 *    `DealVaultPage`.
 */
export default function SafeFilePicker({ open, onClose, onPick }: Props) {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const [files, setFiles] = useState<SafeFile[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError('')
    listMyFiles()
      .then(({ data }) => setFiles(data))
      .catch(() => setFiles([]))
      .finally(() => setLoading(false))
  }, [open])

  if (!open) return null

  const pick = async (id: string) => {
    setBusy(true)
    setError('')
    try {
      await onPick(id)
      onClose()
    } catch {
      setError(t('safe.attachError'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-modal flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t('safe.title')}
        className="bg-white rounded-card p-6 max-w-md w-full space-y-4 shadow-2xl max-h-[90vh] overflow-y-auto"
      >
        <div>
          <h3 className="font-display font-semibold text-lg text-navy">
            {t('safe.title')}
          </h3>
          <p className="text-xs font-body text-navy/50 mt-0.5">{t('safe.hint')}</p>
        </div>

        {loading ? (
          <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
        ) : files.length === 0 ? (
          <p className="text-sm font-body text-navy/50">{t('safe.empty')}</p>
        ) : (
          <div className="space-y-2">
            {files.map((f) => (
              <button
                key={f.id}
                type="button"
                disabled={busy}
                onClick={() => pick(f.id)}
                className="w-full flex items-center justify-between gap-3 p-3 rounded-field border border-navy/10 hover:border-cyan text-left disabled:opacity-50"
              >
                <div className="min-w-0">
                  <p className="text-sm font-body text-navy">
                    {t(`chat.kind.${f.kind}`, { defaultValue: f.kind })}
                  </p>
                  <MonoText className="block text-xs text-navy/40">
                    {t('safe.firstProvided', {
                      date: prefs.date(f.first_provided_at),
                    })}
                  </MonoText>
                </div>
                {/* The scanner's verdict travels with the file. `pending` is not
                    a synonym for safe — it means nobody has looked (T3.8). */}
                {f.scan_status !== 'clean' && (
                  <span className="shrink-0 text-[10px] font-mono uppercase bg-navy/5 text-navy/50 px-1.5 py-0.5 rounded">
                    {t(`safe.scan.${f.scan_status}`, {
                      defaultValue: f.scan_status,
                    })}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {error && <p className="text-xs font-body text-amber">{error}</p>}

        <button
          type="button"
          onClick={onClose}
          className="w-full px-4 py-2 rounded-field border border-navy/15 text-sm font-body text-navy/60 hover:border-navy/40"
        >
          {t('common.close')}
        </button>
      </div>
    </div>
  )
}
