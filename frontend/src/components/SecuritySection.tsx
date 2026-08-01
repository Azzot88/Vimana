import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  cancelEmailChange,
  changeEmail,
  changePassword,
  issueRecoveryCodes,
  requestEmailCode,
  verifyEmail,
  type User,
} from '../api/auth'
import MonoText from './MonoText'
import StepUpDialog from './StepUpDialog'

/** T3.15 — the account's email address and password.
 *
 *  Kept apart from `KeypairSection` on purpose. These are ways *in*; the key is
 *  *who the account is*. Losing a password is an inconvenience, losing the key
 *  ends the identity — putting them in one list would suggest they are the same
 *  kind of thing.
 *
 *  The email change is deliberately two-step. `email` keeps working, verified,
 *  until a code sent to the new address comes back, so a typo costs a retry
 *  rather than the recovery channel — and a stolen session cannot redirect
 *  recovery mail without also reading the new mailbox.
 */
type Pending = 'email' | 'password' | 'recovery' | null

interface Props {
  user: User
  /** `newToken` arrives after a password change, which retires every earlier
   *  session — including this one. The caller must store it before any further
   *  request. */
  onChanged: (newToken?: string) => void | Promise<void>
}

export default function SecuritySection({ user, onChanged }: Props) {
  const { t } = useTranslation()
  const [pending, setPending] = useState<Pending>(null)
  /** Which confirmation dialog is open. Separate from `pending` so the prompt
   *  appears when the user asks for it, not the moment the field looks valid —
   *  and so cancelling the dialog returns to the filled form rather than
   *  discarding what was typed. */
  const [confirming, setConfirming] = useState<Pending>(null)
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  /** T3.16 — the codes exist in the browser for exactly as long as this state
   *  does. They are never re-fetchable: the server holds digests. */
  const [freshCodes, setFreshCodes] = useState<string[] | null>(null)

  const codesLeft = user.recovery_codes_remaining ?? 0

  const pendingEmail = user.pending_email || null

  const reset = () => {
    setPending(null)
    setConfirming(null)
    setNewEmail('')
    setNewPassword('')
    setError('')
  }

  const emailLooksValid = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/.test(newEmail.trim())

  const describe = (err: unknown, fallback: string) => {
    const resp = (err as { response?: { status?: number; data?: { detail?: string } } })
      ?.response
    if (resp?.status === 409 && resp.data?.detail) return resp.data.detail
    return fallback
  }

  const submitEmail = async (token: string) => {
    setBusy(true)
    setError('')
    try {
      await changeEmail(newEmail.trim().toLowerCase(), token)
      reset()
      setNotice(t('security.codeSent') as string)
      await onChanged()
    } catch (err: unknown) {
      setError(describe(err, t('security.emailFailed') as string))
    } finally {
      setBusy(false)
    }
  }

  const submitPassword = async (token: string) => {
    setBusy(true)
    setError('')
    try {
      const { data } = await changePassword(newPassword, token)
      reset()
      setNotice(t('security.passwordChangedSessions') as string)
      // The token in hand was just retired along with every other session —
      // hand the replacement up before anything else calls the API.
      await onChanged(data.access_token)
    } catch {
      setError(t('security.passwordFailed') as string)
    } finally {
      setBusy(false)
    }
  }

  const issueCodes = async (token: string) => {
    setBusy(true)
    setError('')
    try {
      const { data } = await issueRecoveryCodes(token)
      setConfirming(null)
      setFreshCodes(data.codes)
      await onChanged()
    } catch {
      setError(t('security.recoveryFailed') as string)
    } finally {
      setBusy(false)
    }
  }

  const copyCodes = () => {
    if (freshCodes) void navigator.clipboard?.writeText(freshCodes.join('\n'))
  }

  /** Plain text, one code per line — the format that survives being printed,
   *  mailed to yourself or pasted into a password manager. */
  const downloadCodes = () => {
    if (!freshCodes) return
    const blob = new Blob(
      [`${t('security.recoveryFileHeader')}\n\n${freshCodes.join('\n')}\n`],
      { type: 'text/plain' },
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'vimana-recovery-codes.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  const confirmCode = async () => {
    setBusy(true)
    setError('')
    try {
      await verifyEmail(code.trim())
      setCode('')
      setNotice(t('security.emailChanged') as string)
      await onChanged()
    } catch (err: unknown) {
      setError(describe(err, t('security.codeFailed') as string))
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    setError('')
    try {
      await requestEmailCode()
      setNotice(t('security.codeSent') as string)
    } catch {
      setError(t('security.resendFailed') as string)
    }
  }

  const cancel = async () => {
    setError('')
    try {
      await cancelEmailChange()
      setCode('')
      setNotice('')
      await onChanged()
    } catch {
      setError(t('common.errorGeneric') as string)
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-navy/10 p-5 space-y-5">
      <div>
        <h2 className="font-display font-semibold text-lg text-navy">
          {t('security.title')}
        </h2>
        <p className="text-sm font-body text-navy/60 mt-1">{t('security.hint')}</p>
      </div>

      {error && (
        <div className="bg-amber/10 border border-amber/40 rounded-lg px-3 py-2">
          <p className="text-sm font-body text-navy">{error}</p>
        </div>
      )}
      {notice && !error && (
        <div className="bg-cyan/10 border border-cyan/40 rounded-lg px-3 py-2">
          <p className="text-sm font-body text-navy">{notice}</p>
        </div>
      )}

      {/* ── email ── */}
      <div className="space-y-3">
        <div className="text-xs font-body text-navy/50">{t('security.emailLabel')}</div>
        <MonoText className="text-sm text-navy break-all">
          <span data-testid="security-email">{user.email || '—'}</span>
        </MonoText>

        {pendingEmail ? (
          <div className="border border-amber/40 bg-amber/5 rounded-lg p-3 space-y-3">
            <p className="text-sm font-body text-navy">
              {t('security.pendingBody')}{' '}
              <span className="font-medium break-all">{pendingEmail}</span>
            </p>
            <input
              type="text"
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder={t('security.codePlaceholder') as string}
              data-testid="security-code"
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={confirmCode}
                disabled={busy || !code.trim()}
                data-testid="security-confirm-code"
                className="flex-1 bg-navy text-ivory rounded-lg py-2 text-sm font-body font-medium disabled:opacity-40"
              >
                {busy ? '…' : t('security.confirmCode')}
              </button>
              <button
                type="button"
                onClick={resend}
                className="px-3 border border-navy/20 rounded-lg py-2 text-sm font-body text-navy"
              >
                {t('security.resend')}
              </button>
            </div>
            <button
              type="button"
              onClick={cancel}
              data-testid="security-cancel-change"
              className="w-full text-sm font-body text-navy/50"
            >
              {t('security.cancelChange')}
            </button>
          </div>
        ) : pending === 'email' ? (
          <div className="space-y-2">
            <input
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              placeholder={t('security.newEmailPlaceholder') as string}
              autoFocus
              data-testid="security-new-email"
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            />
            <p className="text-xs font-body text-navy/50">
              {t('security.emailNotice')}
            </p>
            <button
              type="button"
              onClick={() => setConfirming('email')}
              disabled={busy || !emailLooksValid}
              data-testid="security-email-continue"
              className="w-full bg-navy text-ivory rounded-lg py-2 text-sm font-body font-medium disabled:opacity-40"
            >
              {busy ? '…' : t('common.continue')}
            </button>
            <button type="button" onClick={reset} className="text-sm font-body text-navy/50">
              {t('common.cancel')}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setPending('email')}
            data-testid="security-change-email"
            className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy"
          >
            {user.email ? t('security.changeEmail') : t('security.addEmail')}
          </button>
        )}
      </div>

      {/* ── password ── */}
      <div className="space-y-3 border-t border-navy/10 pt-4">
        <div className="text-xs font-body text-navy/50">
          {t('security.passwordLabel')}
        </div>
        <p className="text-sm font-body text-navy/60">
          {user.has_password ? t('security.passwordSet') : t('security.passwordNone')}
        </p>

        {pending === 'password' ? (
          <div className="space-y-2">
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder={t('security.newPasswordPlaceholder') as string}
              autoFocus
              data-testid="security-new-password"
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            />
            <p className="text-xs font-body text-navy/50">
              {t('security.passwordNotice')}
            </p>
            {/* Consequence stated before the action, not discovered after it:
                other devices are about to be signed out. */}
            <div className="bg-amber/10 border border-amber/40 rounded-lg px-3 py-2">
              <p className="text-xs font-body text-navy" data-testid="security-sessions-warning">
                {t('security.sessionsWarning')}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setConfirming('password')}
              disabled={busy || newPassword.length < 8}
              data-testid="security-password-continue"
              className="w-full bg-navy text-ivory rounded-lg py-2 text-sm font-body font-medium disabled:opacity-40"
            >
              {busy ? '…' : t('common.continue')}
            </button>
            <button type="button" onClick={reset} className="text-sm font-body text-navy/50">
              {t('common.cancel')}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setPending('password')}
            data-testid="security-change-password"
            className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy"
          >
            {user.has_password
              ? t('security.changePassword')
              : t('security.setPassword')}
          </button>
        )}
      </div>

      {/* ── recovery codes ── */}
      <div className="space-y-3 border-t border-navy/10 pt-4">
        <div className="text-xs font-body text-navy/50">
          {t('security.recoveryLabel')}
        </div>

        {freshCodes ? (
          /* Shown once. Not a warning about danger — a reminder that the server
             keeps digests and physically cannot repeat this screen. */
          <div className="border border-cyan/40 bg-cyan/5 rounded-lg p-3 space-y-3">
            <p className="text-sm font-body text-navy" data-testid="recovery-once">
              {t('security.recoveryOnce')}
            </p>
            <MonoText className="block">
              <ul
                data-testid="recovery-codes"
                className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-navy"
              >
                {freshCodes.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </MonoText>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={downloadCodes}
                data-testid="recovery-download"
                className="flex-1 bg-navy text-ivory rounded-lg py-2 text-sm font-body font-medium"
              >
                {t('security.recoveryDownload')}
              </button>
              <button
                type="button"
                onClick={copyCodes}
                className="px-3 border border-navy/20 rounded-lg py-2 text-sm font-body text-navy"
              >
                {t('security.recoveryCopy')}
              </button>
            </div>
            <button
              type="button"
              onClick={() => setFreshCodes(null)}
              data-testid="recovery-saved"
              className="w-full text-sm font-body text-navy/50"
            >
              {t('security.recoverySaved')}
            </button>
          </div>
        ) : (
          <>
            <p className="text-sm font-body text-navy/60" data-testid="recovery-left">
              {codesLeft > 0
                ? /* `n`, not `count`: i18next treats `count` as the plural
                     selector, and the phrasing is deliberately number-first so
                     no locale needs plural forms at all. */
                  t('security.recoveryLeft', { n: codesLeft })
                : t('security.recoveryNone')}
            </p>
            {/* Low-or-empty is stated where it can be fixed, not as a banner
                following the user around the product. */}
            {codesLeft <= 2 && (
              <div className="bg-amber/10 border border-amber/40 rounded-lg px-3 py-2">
                <p className="text-xs font-body text-navy" data-testid="recovery-warning">
                  {t('security.recoveryWarning')}
                </p>
              </div>
            )}
            <p className="text-xs font-body text-navy/50">
              {/* The honest boundary, and it moves with the rung the account is
                  on (D-KEY-TIERS): a code brings back the way in, and — while
                  the platform still holds a copy of the key — the vaults too. */}
              {user.nostr_pubkey
                ? t('security.recoveryScopeWithKey')
                : t('security.recoveryScope')}
            </p>
            <button
              type="button"
              onClick={() => setConfirming('recovery')}
              disabled={busy}
              data-testid="recovery-generate"
              className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy disabled:opacity-40"
            >
              {codesLeft > 0
                ? t('security.recoveryRegenerate')
                : t('security.recoveryGenerate')}
            </button>
          </>
        )}
      </div>

      {/* Opened by the user, not by the form becoming valid: a grant is
          single-use and lives five minutes, so minting one before they have
          decided to go ahead would spend it for nothing. Cancelling returns to
          the filled form — no retyping. */}
      {confirming === 'email' && (
        <StepUpDialog
          scope="change_email"
          title={t('security.changeEmail') as string}
          body={t('security.emailConfirmBody') as string}
          onConfirm={submitEmail}
          onCancel={() => setConfirming(null)}
        />
      )}
      {confirming === 'password' && (
        <StepUpDialog
          scope="change_password"
          title={
            (user.has_password
              ? t('security.changePassword')
              : t('security.setPassword')) as string
          }
          body={
            `${t('security.passwordConfirmBody')} ${t('security.sessionsWarning')}`
          }
          onConfirm={submitPassword}
          onCancel={() => setConfirming(null)}
        />
      )}
      {confirming === 'recovery' && (
        <StepUpDialog
          scope="add_auth_method"
          title={
            (codesLeft > 0
              ? t('security.recoveryRegenerate')
              : t('security.recoveryGenerate')) as string
          }
          body={t('security.recoveryConfirmBody') as string}
          onConfirm={issueCodes}
          onCancel={() => setConfirming(null)}
        />
      )}
    </div>
  )
}
