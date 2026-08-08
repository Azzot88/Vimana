import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { register, login, me } from '../api/auth'
import NostrAuthButton from '../components/NostrAuthButton'
import PasskeyAuthButton from '../components/PasskeyAuthButton'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { useAuthStore } from '../stores/auth'
import { usePersistedState } from '../hooks/usePersistedState'
import { APP_VERSION } from '../version'

export default function RegisterPage() {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [displayName, setDisplayName] = usePersistedState<string>('register:displayName', '')
  const [email, setEmail] = usePersistedState<string>('register:email', '')
  const [password, setPassword] = useState('')
  const [isCarrier, setIsCarrier] = usePersistedState<boolean>('register:isCarrier', false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register({
        display_name: displayName,
        email,
        password,
        can_carry: isCarrier,
        active_mode: isCarrier ? 'carrier' : 'sender',
        // T_UX.9 — every letter to this account is written in this language.
        locale: i18n.language,
      })
      const { data: tokenData } = await login({ login: email, password })
      localStorage.setItem('token', tokenData.access_token)
      const { data: user } = await me()
      setAuth(user, tokenData.access_token)
      // T3.11 — straight to the code screen unless the address is already
      // proven (e2e auto-verify domain), so the first thing a new user sees is
      // the one action standing between them and creating a deal.
      navigate(user.email_verified ? '/' : '/verify-email')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        setError(t('auth.errorDuplicate'))
      } else {
        setError(t('auth.errorServer'))
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[100dvh] bg-ivory flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* T_UX.10 — the switcher lives in `Navbar`, and `Navbar` lives in
            `Layout`, which only wraps the protected routes. Sign-in and sign-up
            are outside it, so a visitor arriving at a page in the wrong language
            had no way to change it — on the two screens where an unfamiliar
            language costs the most.

            In the flow of the column rather than pinned to the viewport: aligned
            to the card's right edge, it reads as belonging to this form. A fixed
            corner button belongs to the window instead, drifts away from the
            content on a wide screen, and on a short one overlaps it. */}
        <div className="flex justify-end mb-3">
          <LanguageSwitcher />
        </div>
        <h1 className="font-display font-bold text-4xl text-navy text-center mb-2">
          {t('auth.title')}
        </h1>
        <p className="text-center text-navy/50 text-sm font-body mb-8">{t('auth.subtitle')}</p>
        <form onSubmit={handleSubmit} className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              {t('auth.name')}
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
              className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              {t('auth.email')}
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="user@example.com"
            />
          </div>
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              {t('auth.password')}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="••••••••"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={isCarrier}
              onChange={(e) => setIsCarrier(e.target.checked)}
              className="w-4 h-4 accent-cyan"
            />
            <span className="text-sm font-body text-navy">{t('auth.isCarrier')}</span>
          </label>
          {error && (
            <p className="text-xs font-mono text-amber">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-navy text-ivory font-display font-medium py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
          >
            {loading ? t('auth.registering') : t('auth.register')}
          </button>
        </form>
        <div className="mt-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="h-px bg-navy/10 flex-1" />
            <span className="text-xs font-body text-navy/40">
              {t('nostrAuth.or')}
            </span>
            <div className="h-px bg-navy/10 flex-1" />
          </div>
          {/* Signup by key still needs a name — the account has nothing else
              to be known by, and there is no email to fall back on. */}
          <div className="space-y-2">
            <PasskeyAuthButton
              mode="signup"
              displayName={displayName}
              email={email}
            />
            <NostrAuthButton mode="signup" displayName={displayName} />
          </div>
        </div>
        <div className="flex items-center justify-between mt-4">
          <p className="text-xs font-body text-navy/50">
            {t('auth.hasAccount')}{' '}
            <Link to="/login" className="text-cyan hover:underline">
              {t('auth.signIn')}
            </Link>
          </p>
          <span className="font-mono text-xs text-navy/20">v{APP_VERSION}</span>
        </div>
      </div>
    </div>
  )
}
