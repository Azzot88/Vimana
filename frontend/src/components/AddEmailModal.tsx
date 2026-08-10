import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { changeEmail } from '../api/auth'
import StepUpDialog from './StepUpDialog'

/**
 * T_UX.13 — turning on email notifications for an account that has no address.
 *
 * Accounts created by passkey or Nostr key have no email by design (Phase 3.7,
 * owner's decision №2). Until now the switch could be turned on anyway and the
 * only place to actually add an address was another screen, which the profile
 * never mentioned.
 *
 * Deliberately thin. It collects the address and hands off to `changeEmail`,
 * the same endpoint the security screen uses, behind the same step-up
 * ceremony. Re-implementing that flow here would mean two versions of a
 * security-sensitive path that must agree forever; this way there is one, and
 * this file is the doorway to it.
 *
 * Step-up is not skipped for a first address. It looks redundant — there is no
 * old mailbox to protect — but the thing being protected is the account: a
 * stolen session that can attach its own address gets the recovery channel,
 * and for an account with no password that is the whole account.
 *
 * Functions (PROJECT §6.2a):
 * - `AddEmailModal({onClose, onDone})` — default export.
 *   Called by: `pages/ProfilePage`.
 */
interface Props {
  onClose: () => void
  onDone: () => void | Promise<void>
}

export default function AddEmailModal({ onClose, onDone }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const looksValid = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/.test(email.trim())

  const submit = async (stepUpToken: string) => {
    setBusy(true)
    setError('')
    try {
      await changeEmail(email.trim().toLowerCase(), stepUpToken)
      await onDone()
      // The address is claimed, not proven. The code screen is the next step
      // and saying so beats a modal that closes on a job half done.
      navigate('/verify-email')
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number; data?: { detail?: string } } })
        ?.response
      setError(
        resp?.status === 409 && resp.data?.detail
          ? resp.data.detail
          : (t('profile.addEmail.failed') as string),
      )
      setConfirming(false)
    } finally {
      setBusy(false)
    }
  }

  if (confirming) {
    return (
      <StepUpDialog
        scope="change_email"
        title={t('profile.addEmail.title') as string}
        body={t('profile.addEmail.stepUpBody') as string}
        onConfirm={submit}
        onCancel={() => setConfirming(false)}
      />
    )
  }

  return (
    <div className="fixed inset-0 z-modal bg-navy/40 flex items-center justify-center px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-email-title"
        className="w-full max-w-sm bg-white rounded-card p-6 space-y-4"
      >
        <div>
          <h2
            id="add-email-title"
            className="font-display font-bold text-lg text-navy"
          >
            {t('profile.addEmail.title')}
          </h2>
          <p className="text-xs font-body text-muted mt-1 leading-relaxed">
            {t('profile.addEmail.body')}
          </p>
        </div>

        <div>
          <label
            htmlFor="add-email-input"
            className="block text-xs font-body font-medium text-navy/60 mb-1"
          >
            {t('profile.addEmail.label')}
          </label>
          <input
            id="add-email-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
            className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
          />
        </div>

        {error && (
          <p className="text-sm font-body text-danger">{error}</p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-body text-navy/50"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            disabled={!looksValid || busy}
            onClick={() => setConfirming(true)}
            className="px-4 py-2 rounded-field bg-navy text-white text-sm font-body font-medium disabled:opacity-40"
          >
            {t('profile.addEmail.submit')}
          </button>
        </div>
      </div>
    </div>
  )
}
