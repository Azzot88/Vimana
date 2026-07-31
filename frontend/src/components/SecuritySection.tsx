import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  cancelEmailChange,
  changeEmail,
  changePassword,
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
type Pending = 'email' | 'password' | null

interface Props {
  user: User
  onChanged: () => void | Promise<void>
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
      await changePassword(newPassword, token)
      reset()
      setNotice(t('security.passwordChanged') as string)
      await onChanged()
    } catch {
      setError(t('security.passwordFailed') as string)
    } finally {
      setBusy(false)
    }
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
          body={t('security.passwordConfirmBody') as string}
          onConfirm={submitPassword}
          onCancel={() => setConfirming(null)}
        />
      )}
    </div>
  )
}
