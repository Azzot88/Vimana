import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  respondToRequest,
  submitDocument,
  type RespondAction,
  type TargetRole,
  type VerificationRequest,
} from '../api/verification'

const DOC_TYPES = ['passport', 'driver_license', 'national_id', 'other']

interface Props {
  request: VerificationRequest
  yourRole: TargetRole
  onClose: () => void
  onDone: () => void
}

export default function VerificationRespondModal({
  request,
  yourRole,
  onClose,
  onDone,
}: Props) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  const [docType, setDocType] = useState('passport')
  const [docCountry, setDocCountry] = useState('')
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const respond = async (action: RespondAction) => {
    setBusy(true)
    setError('')
    try {
      await respondToRequest(request.deal_id, request.id, action)
      onDone()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : (t('verification.respondError') as string))
    } finally {
      setBusy(false)
    }
  }

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !docCountry) {
      setError(t('verification.pickCountry') as string)
      return
    }
    setBusy(true)
    setError('')
    try {
      await submitDocument(request.deal_id, request.id, file, docType, docCountry.toUpperCase())
      onDone()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : (t('verification.uploadError') as string))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const isCarrier = yourRole === 'carrier'

  return (
    <div
      className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-modal flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-card p-6 max-w-md w-full space-y-4 shadow-2xl"
      >
        <h2 className="font-display font-semibold text-lg text-navy">
          {t('verification.respondTitle')}
        </h2>
        <p className="text-sm font-body text-muted">
          {t(isCarrier ? 'verification.respondCarrierHint' : 'verification.respondSenderHint')}
        </p>

        {!showUpload && (
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setShowUpload(true)}
              disabled={busy}
              className="w-full text-left border border-cyan/40 text-link rounded-field px-4 py-3 text-sm font-body hover:bg-cyan/10 transition-colors"
            >
              📎 {t('verification.actionUpload')}
            </button>
            <button
              type="button"
              onClick={() => respond('later_in_person')}
              disabled={busy}
              className="w-full text-left border border-navy/20 text-navy rounded-field px-4 py-3 text-sm font-body hover:bg-ivory transition-colors"
            >
              🕒 {t('verification.actionLater')}
            </button>
            <button
              type="button"
              onClick={() => respond(isCarrier ? 'declined_polite' : 'declined')}
              disabled={busy}
              className={`w-full text-left border rounded-field px-4 py-3 text-sm font-body transition-colors ${
                isCarrier
                  ? 'border-navy/20 text-muted hover:bg-ivory'
                  : 'border-danger/30 text-danger hover:bg-danger/5'
              }`}
            >
              {isCarrier
                ? `🔒 ${t('verification.actionDeclinePolite')}`
                : `✕ ${t('verification.actionDecline')}`}
            </button>
          </div>
        )}

        {showUpload && (
          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <select
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                className="border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy bg-white focus:outline-none focus:border-cyan"
              >
                {DOC_TYPES.map((d) => (
                  <option key={d} value={d}>
                    {t(`verification.docType.${d}`)}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={docCountry}
                onChange={(e) => setDocCountry(e.target.value.toUpperCase().slice(0, 2))}
                placeholder="AE"
                maxLength={2}
                className="border border-navy/20 rounded-field px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan"
              />
            </div>
            <label className="inline-flex cursor-pointer border border-cyan/40 text-link rounded-field px-4 py-2 text-sm font-display font-medium hover:bg-cyan/10 transition-colors">
              {busy ? '…' : `📎 ${t('verification.chooseFile')}`}
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,application/pdf"
                onChange={upload}
                className="hidden"
                disabled={busy}
              />
            </label>
            <p className="text-[10px] font-mono text-muted">
              🔒 {t('verification.privacyHint')}
            </p>
          </div>
        )}

        {error && <p className="text-xs font-mono text-danger">{error}</p>}

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="text-sm font-body text-muted hover:text-navy px-3 py-2"
          >
            {t('common.cancel')}
          </button>
        </div>
      </div>
    </div>
  )
}
