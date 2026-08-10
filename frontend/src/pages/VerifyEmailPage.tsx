import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import CodeField from '../components/CodeField'
import { me, requestEmailCode, verifyEmail } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import MonoText from '../components/MonoText'

/** T3.11 — email confirmation by 6-digit code.
 *
 *  Confirming gates nothing (owner's decision 2026-07-26): the user can already
 *  do everything. What is at stake is the channel — account recovery and deal
 *  notifications go to this address, and an unproven one may not be theirs. The
 *  copy says exactly that instead of inventing a restriction.
 */
const RESEND_COOLDOWN_SEC = 60

export default function VerifyEmailPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const setAuth = useAuthStore((s) => s.setAuth)

  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SEC)

  useEffect(() => {
    if (cooldown <= 0) return
    const id = window.setTimeout(() => setCooldown((s) => s - 1), 1000)
    return () => window.clearTimeout(id)
  }, [cooldown])

  // Already done (or nothing to prove) — don't strand the user on a dead page.
  useEffect(() => {
    if (user && (user.email_verified || !user.email)) navigate('/dashboard')
  }, [user, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setNotice('')
    setLoading(true)
    try {
      await verifyEmail(code.trim())
      const { data: fresh } = await me()
      if (token) setAuth(fresh, token)
      navigate('/dashboard')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 429) setError(t('verifyEmail.errorTooManyAttempts'))
      else if (status === 400) setError(t('verifyEmail.errorInvalid'))
      else setError(t('common.errorGeneric'))
    } finally {
      setLoading(false)
    }
  }

  const handleResend = async () => {
    setError('')
    setNotice('')
    try {
      await requestEmailCode()
      setNotice(t('verifyEmail.resent'))
      setCooldown(RESEND_COOLDOWN_SEC)
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 429) {
        setError(t('verifyEmail.errorCooldown'))
        setCooldown(RESEND_COOLDOWN_SEC)
      } else {
        setError(t('common.errorGeneric'))
      }
    }
  }

  return (
    <div className="max-w-md mx-auto">
      <div className="bg-white rounded-card border border-navy/10 p-6 space-y-5">
        <div className="space-y-2">
          <h1 className="font-display font-bold text-2xl text-navy">
            {t('verifyEmail.title')}
          </h1>
          <p className="text-sm font-body text-navy/60">
            {t('verifyEmail.sentTo')}{' '}
            <MonoText className="text-navy">{user?.email}</MonoText>
          </p>
          <p className="text-sm font-body text-navy/60">{t('verifyEmail.why')}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <CodeField
              id="verify-code"
              label={t('verifyEmail.codeLabel') as string}
              value={code}
              onChange={setCode}
            />
          </div>

          {error && (
            <div className="bg-amber/10 border border-amber/40 rounded-field px-3 py-2">
              <p className="text-sm font-body text-navy">{error}</p>
            </div>
          )}
          {notice && (
            <p className="text-sm font-body text-navy/60">{notice}</p>
          )}

          <button
            type="submit"
            disabled={loading || code.length !== 6}
            className="w-full bg-navy text-ivory rounded-field py-2.5 text-sm font-body font-medium disabled:opacity-40 transition-opacity"
          >
            {loading ? t('verifyEmail.checking') : t('verifyEmail.submit')}
          </button>
        </form>

        <div className="pt-2 border-t border-navy/10">
          <button
            type="button"
            onClick={handleResend}
            disabled={cooldown > 0}
            className="text-sm font-body text-cyan disabled:text-navy/30 transition-colors"
          >
            {cooldown > 0
              ? t('verifyEmail.resendIn', { seconds: cooldown })
              : t('verifyEmail.resend')}
          </button>
        </div>
      </div>
    </div>
  )
}
