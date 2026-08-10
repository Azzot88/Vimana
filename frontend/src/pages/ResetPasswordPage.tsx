import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { me, resetPassword } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import LanguageSwitcher from '../components/LanguageSwitcher'

/**
 * T_SEC.5 — the screen the reset link lands on.
 *
 * Signs the person in on success rather than sending them back to the login
 * form: making someone type the password they chose thirty seconds ago, into
 * the screen that just took it, protects nobody and reads as a failure.
 *
 * The token never leaves the URL for storage. It is single-use and about to be
 * spent; keeping a copy anywhere would only widen the window in which it is
 * worth stealing.
 */
export default function ResetPasswordPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const setAuth = useAuthStore((s) => s.setAuth)

  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { data } = await resetPassword(token, password)
      localStorage.setItem('token', data.access_token)
      const { data: user } = await me()
      setAuth(user, data.access_token)
      navigate('/dashboard')
    } catch {
      // One message for expired, already-used and wrong: the server does not
      // distinguish them either, and telling them apart would help whoever is
      // guessing more than whoever is recovering.
      setError(t('reset.failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-[100dvh] bg-ivory flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex justify-end mb-3">
          <LanguageSwitcher />
        </div>
        <h1 className="font-display font-bold text-3xl text-navy text-center mb-2">
          {t('reset.title')}
        </h1>
        <p className="text-center text-muted text-sm font-body mb-8">
          {t('reset.subtitle')}
        </p>

        {!token ? (
          <p className="bg-amber/10 border border-amber/40 rounded-field px-4 py-3 text-sm font-body text-navy">
            {t('reset.noToken')}
          </p>
        ) : (
          <form
            onSubmit={submit}
            className="bg-white rounded-card border border-navy/10 p-6 space-y-4"
          >
            <div>
              <label
                htmlFor="reset-password"
                className="block text-xs font-body font-medium text-navy/60 mb-1"
              >
                {t('reset.newPassword')}
              </label>
              <input
                id="reset-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoFocus
                className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
              />
            </div>
            {error && <p className="text-xs font-mono text-amber">{error}</p>}
            <button
              type="submit"
              disabled={busy || password.length < 8}
              className="w-full bg-navy text-ivory font-display font-medium py-3 rounded-field text-sm disabled:opacity-50"
            >
              {busy ? t('reset.saving') : t('reset.submit')}
            </button>
            <p className="text-xs font-body text-muted">{t('reset.sessionsNotice')}</p>
          </form>
        )}
      </div>
    </div>
  )
}
