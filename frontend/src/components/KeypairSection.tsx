import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  declareKeyLost,
  establishIdentity,
  getKeypairStatus,
  requestIdentityChallenge,
  type KeypairStatus,
} from '../api/keypair'
import {
  generateKeypair,
  keyBackupText,
  signProofWithKey,
  signProofWithNip07,
  type Keypair,
} from '../lib/identity'
import { hasNip07Extension } from '../lib/nostr'
import MonoText from './MonoText'

/** T3.12 pt.4 — the account's key, in three honest states.
 *
 *  1. **Service key.** The platform generated it and holds it. It encrypts this
 *     user's vault and signs their records, but it is not shown as "your key"
 *     and never leaves the platform — calling it an identity would be a claim
 *     we cannot back.
 *  2. **Own identity.** Generated in this browser or brought from a NIP-07
 *     extension. The platform has only the public half.
 *  3. **Key lost.** Terminal. The account can still be signed into but can no
 *     longer act.
 *
 *  There is no "take the key we made for you" button any more: a key that sat
 *  on our disks cannot be proven deleted, so the transition always mints a new
 *  one.
 */
type Step = 'idle' | 'choose' | 'showKey' | 'lost'

export default function KeypairSection() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<KeypairStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [step, setStep] = useState<Step>('idle')
  const [generated, setGenerated] = useState<Keypair | null>(null)
  const [saved, setSaved] = useState(false)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const nip07 = hasNip07Extension()

  const load = async () => {
    try {
      const { data } = await getKeypairStatus()
      setStatus(data)
    } catch {
      // Section simply stays empty — not worth an error banner on a profile.
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const reset = () => {
    setStep('idle')
    setGenerated(null)
    setSaved(false)
    setPassword('')
    setError('')
  }

  /** Generate locally, then show the key before anything is sent. The user must
   *  confirm they saved it — losing it after the transition is unrecoverable. */
  const handleGenerate = () => {
    setError('')
    setGenerated(generateKeypair())
    setSaved(false)
    setStep('showKey')
  }

  const submitProof = async (
    sign: (challenge: string) => Promise<ReturnType<typeof signProofWithKey> | null>,
  ) => {
    setBusy(true)
    setError('')
    try {
      const { data: ch } = await requestIdentityChallenge()
      const proof = await sign(ch.challenge)
      if (!proof) {
        setError(t('profile.identity.errorNoExtension') as string)
        return
      }
      const { data } = await establishIdentity(proof)
      setStatus(data)
      reset()
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number; data?: { detail?: string } } })
        ?.response
      if (resp?.status === 409 && resp.data?.detail) {
        // Blockers (e2e vault messages) come back explained — show them.
        setError(resp.data.detail)
      } else if (resp?.status === 401) {
        setError(t('profile.identity.errorProof') as string)
      } else {
        setError(t('profile.identity.errorGeneric') as string)
      }
    } finally {
      setBusy(false)
    }
  }

  const handleConfirmGenerated = () =>
    submitProof(async (challenge) =>
      generated ? signProofWithKey(generated, challenge) : null,
    )

  const handleUseNip07 = () =>
    submitProof((challenge) => signProofWithNip07(challenge))

  const handleDeclareLost = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await declareKeyLost(password)
      setStatus(data)
      reset()
    } catch (err: unknown) {
      const st = (err as { response?: { status?: number } })?.response?.status
      setError(
        st === 401
          ? (t('profile.identity.errorPassword') as string)
          : (t('profile.identity.errorGeneric') as string),
      )
    } finally {
      setBusy(false)
    }
  }

  const copyBackup = async () => {
    if (!generated) return
    try {
      await navigator.clipboard.writeText(keyBackupText(generated))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard blocked — the key is on screen to copy by hand.
    }
  }

  const downloadBackup = () => {
    if (!generated) return
    const blob = new Blob([keyBackupText(generated)], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `vimana-key-${generated.npubHex.slice(0, 8)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading || !status) return null

  const established = status.identity_established
  const lost = status.key_lost

  return (
    <div className="bg-white rounded-2xl border border-navy/10 p-5 space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display font-semibold text-lg text-navy">
          {t('profile.identity.title')}
        </h2>
        <span
          data-testid="identity-state"
          data-state={lost ? 'lost' : established ? 'own' : 'service'}
          className={`text-xs font-body px-2 py-0.5 rounded ${
            lost
              ? 'bg-navy/10 text-navy/50'
              : established
                ? 'bg-cyan/10 text-cyan'
                : 'bg-navy/5 text-navy/60'
          }`}
        >
          {lost
            ? t('profile.identity.stateLost')
            : established
              ? t('profile.identity.stateOwn')
              : t('profile.identity.stateService')}
        </span>
      </div>

      <p className="text-sm font-body text-navy/60">
        {lost
          ? t('profile.identity.hintLost')
          : established
            ? t('profile.identity.hintOwn')
            : t('profile.identity.hintService')}
      </p>

      {established && status.npub && (
        <div>
          <div className="text-xs font-body text-navy/50 mb-1">
            {t('profile.identity.npubLabel')}
          </div>
          <MonoText className="text-xs text-navy break-all">
            <span data-testid="identity-npub">{status.npub}</span>
          </MonoText>
        </div>
      )}

      {error && (
        <div className="bg-amber/10 border border-amber/40 rounded-lg px-3 py-2">
          <p className="text-sm font-body text-navy">{error}</p>
        </div>
      )}

      {/* ── not established yet ── */}
      {!established && !lost && step === 'idle' && (
        <button
          type="button"
          data-testid="identity-start"
          onClick={() => setStep('choose')}
          className="w-full bg-navy text-ivory rounded-lg py-2.5 text-sm font-body font-medium"
        >
          {t('profile.identity.startCta')}
        </button>
      )}

      {!established && step === 'choose' && (
        <div className="space-y-3">
          <div className="bg-amber/10 border border-amber/40 rounded-lg px-3 py-2 space-y-1">
            <p className="text-sm font-body text-navy font-medium">
              {t('profile.identity.warnTitle')}
            </p>
            <p className="text-sm font-body text-navy/70">
              {t('profile.identity.warnBody')}
            </p>
          </div>
          <button
            type="button"
            data-testid="identity-generate"
            onClick={handleGenerate}
            className="w-full bg-navy text-ivory rounded-lg py-2.5 text-sm font-body font-medium"
          >
            {t('profile.identity.generateCta')}
          </button>
          <button
            type="button"
            onClick={handleUseNip07}
            disabled={!nip07 || busy}
            className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy disabled:opacity-40"
          >
            {nip07
              ? t('profile.identity.nip07Cta')
              : t('profile.identity.nip07Missing')}
          </button>
          <button
            type="button"
            onClick={reset}
            className="w-full text-sm font-body text-navy/50"
          >
            {t('common.cancel')}
          </button>
        </div>
      )}

      {/* ── key generated, not yet sent ── */}
      {step === 'showKey' && generated && (
        <div className="space-y-3">
          <p className="text-sm font-body text-navy">
            {t('profile.identity.saveKeyBody')}
          </p>
          <div className="bg-navy/5 rounded-lg p-3 space-y-2">
            <div>
              <div className="text-xs font-body text-navy/50">
                {t('profile.identity.npubLabel')}
              </div>
              <MonoText className="text-xs text-navy break-all">
                {generated.npubHex}
              </MonoText>
            </div>
            <div>
              <div className="text-xs font-body text-navy/50">
                {t('profile.identity.nsecLabel')}
              </div>
              <MonoText className="text-xs text-navy break-all">
                {generated.nsecHex}
              </MonoText>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={downloadBackup}
              className="flex-1 border border-navy/20 rounded-lg py-2 text-sm font-body text-navy"
            >
              {t('profile.identity.download')}
            </button>
            <button
              type="button"
              onClick={copyBackup}
              className="flex-1 border border-navy/20 rounded-lg py-2 text-sm font-body text-navy"
            >
              {copied ? t('common.copied') : t('profile.identity.copy')}
            </button>
          </div>
          <label className="flex items-start gap-2 text-sm font-body text-navy">
            <input
              type="checkbox"
              data-testid="identity-saved"
              checked={saved}
              onChange={(e) => setSaved(e.target.checked)}
              className="mt-1"
            />
            <span>{t('profile.identity.savedConfirm')}</span>
          </label>
          <button
            type="button"
            data-testid="identity-confirm"
            onClick={handleConfirmGenerated}
            disabled={!saved || busy}
            className="w-full bg-navy text-ivory rounded-lg py-2.5 text-sm font-body font-medium disabled:opacity-40"
          >
            {busy ? '…' : t('profile.identity.confirmCta')}
          </button>
          <button
            type="button"
            onClick={reset}
            className="w-full text-sm font-body text-navy/50"
          >
            {t('common.cancel')}
          </button>
        </div>
      )}

      {/* ── established: the only remaining action is declaring it lost ── */}
      {established && !lost && step === 'idle' && (
        <button
          type="button"
          onClick={() => setStep('lost')}
          className="text-sm font-body text-navy/50 underline underline-offset-2"
        >
          {t('profile.identity.declareLostCta')}
        </button>
      )}

      {established && step === 'lost' && (
        <div className="space-y-3">
          <div className="bg-amber/10 border border-amber/40 rounded-lg px-3 py-2">
            <p className="text-sm font-body text-navy">
              {t('profile.identity.declareLostWarn')}
            </p>
          </div>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('profile.identity.passwordPlaceholder') as string}
            className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy"
          />
          <button
            type="button"
            onClick={handleDeclareLost}
            disabled={busy || !password}
            className="w-full bg-navy text-ivory rounded-lg py-2.5 text-sm font-body font-medium disabled:opacity-40"
          >
            {busy ? '…' : t('profile.identity.declareLostConfirm')}
          </button>
          <button
            type="button"
            onClick={reset}
            className="w-full text-sm font-body text-navy/50"
          >
            {t('common.cancel')}
          </button>
        </div>
      )}
    </div>
  )
}
