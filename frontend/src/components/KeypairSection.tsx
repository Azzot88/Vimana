import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  declareKeyLost,
  deletePlatformCopy,
  establishIdentity,
  getKeypairStatus,
  releaseKeyForVault,
  requestIdentityChallenge,
  type KeypairStatus,
} from '../api/keypair'
import {
  buildIdentityVault,
  generateKeypair,
  keyBackupText,
  npubFromNsec,
  parseNsecInput,
  shortKey,
  signProofWithKey,
  signProofWithNip07,
  type Keypair,
} from '../lib/identity'
import { hasNip07Extension } from '../lib/nostr'
import MonoText from './MonoText'
import StepUpDialog from './StepUpDialog'

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
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  /** T3.21 — Identity Vault download. The passphrase lives in this state and
   *  nowhere else: it is never sent, and sealing happens in this tab. */
  const [vaultPass, setVaultPass] = useState('')
  const [vaultOpen, setVaultOpen] = useState(false)
  const [confirmingVault, setConfirmingVault] = useState(false)
  const [vaultDone, setVaultDone] = useState(false)
  /** T3.22 — dropping our copy of the key: the one irreversible step. */
  /** T3.24 pt.1 — sealing a key the user already holds. Nothing here touches
   *  the network: the key is pasted, sealed and downloaded in this tab. */
  /** T3.23 pt.2 — the tick in front of replacing an identity that already exists. */
  const [swapUnderstood, setSwapUnderstood] = useState(false)
  const [sealOpen, setSealOpen] = useState(false)
  const [sealKey, setSealKey] = useState('')
  const [dropOpen, setDropOpen] = useState(false)
  const [dropUnderstood, setDropUnderstood] = useState(false)
  const [confirmingDrop, setConfirmingDrop] = useState(false)

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

  /** T3.15 — confirmation comes from step-up, so an account with no password
   *  can do this too. It used to take a password field, which locked out
   *  exactly the people most likely to lose a key. */
  const handleDeclareLost = async (token: string) => {
    setBusy(true)
    setError('')
    try {
      const { data } = await declareKeyLost(token)
      setStatus(data)
      reset()
    } catch {
      setError(t('profile.identity.errorGeneric') as string)
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
    // BOM + charset, same reason as the recovery codes file: without them
    // Notepad decodes UTF-8 as cp1251.
    const blob = new Blob(['﻿', keyBackupText(generated)], {
      type: 'text/plain;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `vimana-key-${generated.npubHex.slice(0, 8)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  /** T3.21 — the whole of rung 2, in one function: ask the server for the key,
   *  seal it here under a passphrase it never sees, hand the user a file. */
  const downloadVault = async (stepUpToken: string) => {
    setBusy(true)
    setError('')
    try {
      const { data } = await releaseKeyForVault(stepUpToken)
      const file = buildIdentityVault(data.npub_hex, data.nsec_hex, vaultPass)
      const blob = new Blob([JSON.stringify(file, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      // The name no longer carries the npub: the file stopped announcing whose
      // it is inside, and a filename that still did would undo that.
      a.download = `vimana-identity-${new Date().toISOString().slice(0, 10)}.dvlt`
      a.click()
      URL.revokeObjectURL(url)
      setConfirmingVault(false)
      setVaultOpen(false)
      setVaultPass('')
      setVaultDone(true)
      await load()
    } catch {
      setError(t('profile.identity.vaultFailed') as string)
    } finally {
      setBusy(false)
    }
  }

  /** T3.24 pt.1 — turn a key the user already has into an Identity Vault,
   *  entirely offline. The npub is derived from the key itself rather than
   *  taken from the account: the file must describe what it actually contains. */
  const sealExistingKey = () => {
    setBusy(true)
    setError('')
    try {
      const nsecHex = parseNsecInput(sealKey)
      const file = buildIdentityVault(npubFromNsec(nsecHex), nsecHex, vaultPass)
      const blob = new Blob([JSON.stringify(file, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `vimana-identity-${new Date().toISOString().slice(0, 10)}.dvlt`
      a.click()
      URL.revokeObjectURL(url)
      setSealOpen(false)
      setSealKey('')
      setVaultPass('')
      setVaultDone(true)
    } catch {
      setError(t('profile.identity.sealFailed') as string)
    } finally {
      setBusy(false)
    }
  }

  /** T3.22 — rung 3. Nothing about the identity changes; what ends is our
   *  ability to act for it, and it ends in the database rather than in a
   *  promise. */
  const dropPlatformCopy = async (stepUpToken: string) => {
    setBusy(true)
    setError('')
    try {
      const { data } = await deletePlatformCopy(stepUpToken)
      setStatus(data)
      setConfirmingDrop(false)
      setDropOpen(false)
      setDropUnderstood(false)
    } catch {
      setError(t('profile.identity.errorGeneric') as string)
    } finally {
      setBusy(false)
    }
  }

  if (loading || !status) return null

  const established = status.identity_established
  const lost = status.key_lost
  const copies = status.key_copies

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
          {/* Shortened on purpose: sixty-four hex characters are unreadable and
              nobody compares them by eye anyway. Four and four is enough to
              recognise a key you know, and the full value is one click away. */}
          <MonoText className="text-sm text-navy">
            <span data-testid="identity-npub" title={status.npub}>
              {shortKey(status.npub)}
            </span>
          </MonoText>
          <button
            type="button"
            onClick={() => void navigator.clipboard?.writeText(status.npub || '')}
            className="text-xs font-body text-cyan hover:underline mt-1"
          >
            {t('profile.identity.copyNpub')}
          </button>
        </div>
      )}

      {/* T3.23 — the key changed at some point, and everything signed before
          that stays signed by the old one. Stated with its date: a bare "your
          key" would let someone assume today's key covers yesterday's records. */}
      {status.previous_npub && status.identity_changed_at && (
        <div className="bg-navy/5 rounded-lg px-3 py-2 space-y-0.5">
          <p className="text-xs font-body text-navy/70" data-testid="identity-changed">
            {t('profile.identity.changedOn', {
              date: new Date(status.identity_changed_at).toLocaleDateString(),
            })}
          </p>
          <p className="text-xs font-body text-navy/50">
            {t('profile.identity.previousKey')}{' '}
            <span className="font-mono" title={status.previous_npub}>
              {shortKey(status.previous_npub)}
            </span>
          </p>
        </div>
      )}

      {error && (
        <div className="bg-amber/10 border border-amber/40 rounded-lg px-3 py-2">
          <p className="text-sm font-body text-navy">{error}</p>
        </div>
      )}

      {/* ── T3.21 — Identity Vault: the rung, and the way up to the next ── */}
      {!lost && (
        <div className="border-t border-navy/10 pt-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-body text-navy/50">
              {t('profile.identity.vaultLabel')}
            </div>
            <span
              data-testid="identity-copies"
              data-copies={copies}
              className="text-xs font-body text-navy/50"
            >
              {t(`profile.identity.copies.${copies}`)}
            </span>
          </div>

          {vaultDone && (
            <div className="bg-cyan/10 border border-cyan/40 rounded-lg px-3 py-2">
              <p className="text-xs font-body text-navy" data-testid="vault-done">
                {t('profile.identity.vaultDone')}
              </p>
            </div>
          )}

          {copies === 'user_only' ? (
            /* T3.24 pt.1 — the platform has nothing to hand over, but sealing
               needs nothing from it either: paste the key you already hold and
               the browser turns it into an Identity Vault. This exists because
               accounts that took the old T3.12 path were left holding a .txt
               with the key in clear text. */
            <div className="space-y-2">
              <p className="text-sm font-body text-navy/60">
                {t('profile.identity.vaultOnlyYours')}
              </p>
              {sealOpen ? (
                <>
                  <textarea
                    value={sealKey}
                    onChange={(e) => setSealKey(e.target.value)}
                    rows={2}
                    placeholder={t('profile.identity.sealKeyPlaceholder') as string}
                    data-testid="seal-key"
                    className="w-full border border-navy/20 rounded-lg px-3 py-2 text-xs font-mono text-navy focus:outline-none focus:border-cyan"
                  />
                  <input
                    type="password"
                    value={vaultPass}
                    onChange={(e) => setVaultPass(e.target.value)}
                    placeholder={t('profile.identity.vaultPassPlaceholder') as string}
                    className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
                  />
                  <p className="text-xs font-body text-navy/50">
                    {t('profile.identity.sealLocalNotice')}
                  </p>
                  <button
                    type="button"
                    onClick={sealExistingKey}
                    disabled={busy || vaultPass.length < 8 || !sealKey.trim()}
                    data-testid="seal-continue"
                    className="w-full bg-navy text-ivory rounded-lg py-2 text-sm font-body font-medium disabled:opacity-40"
                  >
                    {busy ? '…' : t('profile.identity.sealCta')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSealOpen(false)
                      setSealKey('')
                      setVaultPass('')
                    }}
                    className="text-sm font-body text-navy/50"
                  >
                    {t('common.cancel')}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => setSealOpen(true)}
                  data-testid="seal-open"
                  className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy"
                >
                  {t('profile.identity.sealCta')}
                </button>
              )}
            </div>
          ) : vaultOpen ? (
            <div className="space-y-2">
              <input
                type="password"
                value={vaultPass}
                onChange={(e) => setVaultPass(e.target.value)}
                placeholder={t('profile.identity.vaultPassPlaceholder') as string}
                autoFocus
                data-testid="vault-passphrase"
                className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
              />
              {/* Reassuring, not frightening: at this rung nothing is at stake
                  yet — the platform still holds a copy, so a forgotten
                  passphrase costs one more download, not the identity. */}
              <p className="text-xs font-body text-navy/50">
                {t('profile.identity.vaultPassNotice')}
              </p>
              <button
                type="button"
                onClick={() => setConfirmingVault(true)}
                disabled={busy || vaultPass.length < 8}
                data-testid="vault-continue"
                className="w-full bg-navy text-ivory rounded-lg py-2 text-sm font-body font-medium disabled:opacity-40"
              >
                {busy ? '…' : t('common.continue')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setVaultOpen(false)
                  setVaultPass('')
                }}
                className="text-sm font-body text-navy/50"
              >
                {t('common.cancel')}
              </button>
            </div>
          ) : (
            <>
              <p className="text-sm font-body text-navy/60">
                {t('profile.identity.vaultHint')}
              </p>
              <button
                type="button"
                onClick={() => setVaultOpen(true)}
                data-testid="vault-download"
                className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy"
              >
                {copies === 'both'
                  ? t('profile.identity.vaultDownloadAgain')
                  : t('profile.identity.vaultDownload')}
              </button>
            </>
          )}
        </div>
      )}

      {confirmingVault && (
        <StepUpDialog
          scope="add_auth_method"
          title={t('profile.identity.vaultDownload') as string}
          body={t('profile.identity.vaultConfirmBody') as string}
          onConfirm={downloadVault}
          onCancel={() => setConfirmingVault(false)}
        />
      )}

      {/* ── T3.22 — rung 2 → 3: we stop holding a copy ──
          Only offered once a copy exists on the user's side. Before that this
          button would be an identity shredder one click deep, and the backend
          refuses it for the same reason (409). */}
      {!lost && copies === 'both' && (
        <div className="border-t border-navy/10 pt-4 space-y-3">
          {dropOpen ? (
            <div className="border border-amber/40 bg-amber/5 rounded-lg p-3 space-y-3">
              <p className="text-sm font-body text-navy font-medium">
                {t('profile.identity.dropTitle')}
              </p>
              <p className="text-sm font-body text-navy/70">
                {t('profile.identity.dropBody')}
              </p>
              <label className="flex items-start gap-2 text-sm font-body text-navy">
                <input
                  type="checkbox"
                  checked={dropUnderstood}
                  onChange={(e) => setDropUnderstood(e.target.checked)}
                  data-testid="drop-understood"
                  className="mt-1"
                />
                <span>{t('profile.identity.dropCheckbox')}</span>
              </label>
              <button
                type="button"
                onClick={() => setConfirmingDrop(true)}
                disabled={!dropUnderstood || busy}
                data-testid="drop-continue"
                className="w-full bg-navy text-ivory rounded-lg py-2 text-sm font-body font-medium disabled:opacity-40"
              >
                {busy ? '…' : t('profile.identity.dropCta')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDropOpen(false)
                  setDropUnderstood(false)
                }}
                className="w-full text-sm font-body text-navy/50"
              >
                {t('common.cancel')}
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setDropOpen(true)}
              data-testid="drop-platform-copy"
              className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy"
            >
              {t('profile.identity.dropCta')}
            </button>
          )}
        </div>
      )}

      {confirmingDrop && (
        <StepUpDialog
          scope="declare_lost"
          title={t('profile.identity.dropCta') as string}
          body={t('profile.identity.dropConfirmBody') as string}
          onConfirm={dropPlatformCopy}
          onCancel={() => setConfirmingDrop(false)}
        />
      )}

      {/* ── replacing the identity with a different key ──
          Deliberately quiet and deliberately last. Under `D-KEY-TIERS` owning
          your key is reached by removing our copy (above), not by minting a new
          one — this path exists for someone bringing a key from elsewhere, and
          it *replaces* the identity rather than upgrading it. It used to be the
          headline button here, which is how an owner walked into it on
          2026-08-01 and ended up with a plaintext .txt. */}
      {!established && !lost && step === 'idle' && (
        <button
          type="button"
          data-testid="identity-start"
          onClick={() => setStep('choose')}
          className="w-full text-sm font-body text-navy/50 underline"
        >
          {t('profile.identity.startCta')}
        </button>
      )}

      {step === 'choose' && (
        <div className="space-y-3">
          <div className="bg-amber/10 border border-amber/40 rounded-lg px-3 py-2 space-y-1">
            <p className="text-sm font-body text-navy font-medium">
              {t('profile.identity.warnTitle')}
            </p>
            <p className="text-sm font-body text-navy/70">
              {t('profile.identity.warnBody')}
            </p>
            {/* T3.23 pt.2 — for an account that already has an identity this is
                not a first step but a replacement: everything signed before
                stays signed by a key the account no longer has. That deserves
                the same deliberate tick as deleting our copy. */}
            {established && (
              <label className="flex items-start gap-2 text-sm font-body text-navy pt-1">
                <input
                  type="checkbox"
                  checked={swapUnderstood}
                  onChange={(e) => setSwapUnderstood(e.target.checked)}
                  data-testid="identity-swap-understood"
                  className="mt-1"
                />
                <span>{t('profile.identity.swapCheckbox')}</span>
              </label>
            )}
          </div>
          <button
            type="button"
            data-testid="identity-generate"
            onClick={handleGenerate}
            disabled={established && !swapUnderstood}
            className="w-full bg-navy text-ivory rounded-lg py-2.5 text-sm font-body font-medium disabled:opacity-40"
          >
            {t('profile.identity.generateCta')}
          </button>
          <button
            type="button"
            onClick={handleUseNip07}
            disabled={!nip07 || busy || (established && !swapUnderstood)}
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
        <StepUpDialog
          scope="declare_lost"
          title={t('profile.identity.declareLostCta') as string}
          body={t('profile.identity.declareLostWarn') as string}
          onConfirm={handleDeclareLost}
          onCancel={reset}
        />
      )}
    </div>
  )
}
