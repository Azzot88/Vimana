import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  exportKeypair,
  getKeypairStatus,
  importKeypair,
  type KeypairStatus,
} from '../api/keypair'
import { hasNip07Extension } from '../lib/nostr'
import MonoText from './MonoText'

type Modal = 'none' | 'export' | 'import'

export default function KeypairSection() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<KeypairStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<Modal>('none')
  const [password, setPassword] = useState('')
  const [exportedNsec, setExportedNsec] = useState<string | null>(null)
  const [importValue, setImportValue] = useState('')
  const [importMode, setImportMode] = useState<'nsec' | 'npub'>('nsec')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const nip07 = hasNip07Extension()

  const load = async () => {
    try {
      const { data } = await getKeypairStatus()
      setStatus(data)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleExport = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await exportKeypair(password)
      setExportedNsec(data.nsec_hex)
      setPassword('')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setError(
        status === 401
          ? (t('profile.keypair.exportBadPassword') as string)
          : (t('profile.keypair.exportError') as string),
      )
    } finally {
      setBusy(false)
    }
  }

  const handleImport = async () => {
    setBusy(true)
    setError('')
    try {
      const payload =
        importMode === 'nsec'
          ? { nsec_hex: importValue.trim().toLowerCase() }
          : { npub_hex: importValue.trim().toLowerCase() }
      const { data } = await importKeypair(payload)
      setStatus(data)
      setImportValue('')
      setModal('none')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(
        typeof detail === 'string' ? detail : (t('profile.keypair.importError') as string),
      )
    } finally {
      setBusy(false)
    }
  }

  const handleCopy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // ignore
    }
  }

  const closeModal = () => {
    setModal('none')
    setPassword('')
    setExportedNsec(null)
    setImportValue('')
    setError('')
  }

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-2">
        <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display font-semibold text-base text-navy">
          {t('profile.keypair.title')}
        </h2>
        <span
          className={`text-xs font-mono px-2 py-0.5 rounded ${
            status?.key_self_custody
              ? 'bg-amber/20 text-amber'
              : 'bg-cyan/20 text-cyan'
          }`}
        >
          {status?.key_self_custody
            ? t('profile.keypair.selfCustody')
            : t('profile.keypair.custodial')}
        </span>
      </div>

      <div>
        <p className="text-xs font-body font-medium text-navy/60 mb-1">
          {t('profile.keypair.npubLabel')}
        </p>
        {status?.npub ? (
          <div className="flex items-center gap-2">
            <MonoText className="text-xs text-navy/70 break-all">
              {status.npub}
            </MonoText>
            <button
              type="button"
              onClick={() => handleCopy(status.npub!)}
              className="text-xs font-body text-cyan hover:underline shrink-0"
            >
              {copied ? t('chat.addressCard.copied') : t('chat.addressCard.copy')}
            </button>
          </div>
        ) : (
          <p className="text-xs font-mono text-navy/40">—</p>
        )}
      </div>

      <p className="text-xs font-body text-navy/50">
        {status?.key_self_custody
          ? t('profile.keypair.selfCustodyHint')
          : t('profile.keypair.custodialHint')}
      </p>

      {nip07 && (
        <div className="bg-cyan/5 border border-cyan/30 rounded-lg px-3 py-2">
          <p className="text-xs font-body text-navy">
            🔌 {t('profile.keypair.nip07Detected')}
          </p>
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-2 border-t border-navy/5">
        {status?.has_encrypted_nsec && (
          <button
            type="button"
            onClick={() => setModal('export')}
            className="text-xs font-display font-medium border border-navy/20 text-navy px-3 py-1.5 rounded-lg hover:bg-ivory"
          >
            {t('profile.keypair.export')}
          </button>
        )}
        <button
          type="button"
          onClick={() => setModal('import')}
          className="text-xs font-display font-medium border border-navy/20 text-navy px-3 py-1.5 rounded-lg hover:bg-ivory"
        >
          {t('profile.keypair.import')}
        </button>
      </div>

      {modal === 'export' && (
        <div
          className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={closeModal}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <h3 className="font-display font-semibold text-lg text-navy">
              {t('profile.keypair.exportTitle')}
            </h3>

            {!exportedNsec ? (
              <>
                <p className="text-sm font-body text-navy/60">
                  {t('profile.keypair.exportHint')}
                </p>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('auth.password') as string}
                  autoFocus
                  className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
                />
                {error && <p className="text-xs font-mono text-red-600">{error}</p>}
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={closeModal}
                    className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    onClick={handleExport}
                    disabled={busy || !password}
                    className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid disabled:opacity-40"
                  >
                    {busy ? '…' : t('profile.keypair.export')}
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm font-body text-red-700 bg-red-50 rounded-lg px-3 py-2">
                  ⚠️ {t('profile.keypair.exportWarn')}
                </p>
                <div>
                  <p className="text-xs font-body font-medium text-navy/60 mb-1">
                    nsec_hex
                  </p>
                  <MonoText className="text-xs text-navy break-all bg-ivory p-2 rounded block">
                    {exportedNsec}
                  </MonoText>
                  <button
                    type="button"
                    onClick={() => handleCopy(exportedNsec)}
                    className="text-xs font-body text-cyan hover:underline mt-1"
                  >
                    {copied ? t('chat.addressCard.copied') : t('chat.addressCard.copy')}
                  </button>
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={closeModal}
                    className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid"
                  >
                    {t('common.close')}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {modal === 'import' && (
        <div
          className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={closeModal}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <h3 className="font-display font-semibold text-lg text-navy">
              {t('profile.keypair.importTitle')}
            </h3>
            <p className="text-sm font-body text-navy/60">
              {t('profile.keypair.importHint')}
            </p>
            <div className="flex gap-2">
              <label className="flex items-center gap-2 text-xs font-body text-navy/70">
                <input
                  type="radio"
                  name="import-mode"
                  checked={importMode === 'nsec'}
                  onChange={() => setImportMode('nsec')}
                />
                nsec (private)
              </label>
              <label className="flex items-center gap-2 text-xs font-body text-navy/70">
                <input
                  type="radio"
                  name="import-mode"
                  checked={importMode === 'npub'}
                  onChange={() => setImportMode('npub')}
                />
                npub (public only)
              </label>
            </div>
            <textarea
              value={importValue}
              onChange={(e) => setImportValue(e.target.value)}
              rows={2}
              placeholder={
                importMode === 'nsec'
                  ? '64 hex chars (nsec)'
                  : '64 hex chars (npub)'
              }
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-xs font-mono text-navy focus:outline-none focus:border-cyan"
            />
            {error && <p className="text-xs font-mono text-red-600">{error}</p>}
            <div className="flex gap-2 justify-end">
              <button
                onClick={closeModal}
                className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleImport}
                disabled={busy || !importValue.trim()}
                className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid disabled:opacity-40"
              >
                {busy ? '…' : t('profile.keypair.import')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
