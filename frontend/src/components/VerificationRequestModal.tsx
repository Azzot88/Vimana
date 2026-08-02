import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { createRequest, type TargetRole } from '../api/verification'

interface Props {
  dealId: string
  targetRole: TargetRole
  onClose: () => void
  onCreated: (reqId: string) => void
}

export default function VerificationRequestModal({
  dealId,
  targetRole,
  onClose,
  onCreated,
}: Props) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const handleCreate = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await createRequest(dealId, targetRole)
      onCreated(data.id)
    } catch {
      setError(t('verification.requestError') as string)
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
        className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl"
      >
        <h2 className="font-display font-semibold text-lg text-navy">
          {t(
            targetRole === 'sender'
              ? 'verification.askSenderTitle'
              : 'verification.askCarrierTitle',
          )}
        </h2>
        <p className="text-sm font-body text-navy/60">
          {t(
            targetRole === 'sender'
              ? 'verification.askSenderHint'
              : 'verification.askCarrierHint',
          )}
        </p>
        {error && <p className="text-xs font-mono text-danger">{error}</p>}
        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={handleCreate}
            disabled={busy}
            className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid disabled:opacity-40"
          >
            {busy ? '…' : t('verification.sendRequest')}
          </button>
        </div>
      </div>
    </div>
  )
}
