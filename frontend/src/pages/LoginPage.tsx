import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { login, me } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { usePersistedState } from '../hooks/usePersistedState'
import { APP_VERSION } from '../version'

export default function LoginPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const inactivityLogout = searchParams.get('reason') === 'inactivity'
  const setAuth = useAuthStore((s) => s.setAuth)
  const [loginVal, setLoginVal] = usePersistedState<string>('login:login', '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data: tokenData } = await login({ login: loginVal, password })
      localStorage.setItem('token', tokenData.access_token)
      const { data: user } = await me()
      setAuth(user, tokenData.access_token)
      navigate('/')
    } catch {
      setError(t('auth.errorCredentials'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-ivory flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="font-display font-bold text-4xl text-navy text-center mb-2">
          {t('auth.title')}
        </h1>
        <p className="text-center text-navy/50 text-sm font-body mb-8">{t('auth.subtitle')}</p>
        {inactivityLogout && (
          <div className="bg-amber/10 border border-amber/40 rounded-lg px-4 py-3 mb-4">
            <p className="text-sm font-body text-navy">
              {t('auth.inactivityLoggedOut')}
            </p>
          </div>
        )}
        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              {t('auth.emailOrPhone')}
            </label>
            <input
              type="text"
              value={loginVal}
              onChange={(e) => setLoginVal(e.target.value)}
              required
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
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
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p className="text-xs font-mono text-orange-600">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-navy text-ivory font-display font-medium py-3 min-h-[2.75rem] rounded-lg text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
          >
            {loading ? t('auth.logging') : t('auth.login')}
          </button>
        </form>
        <div className="flex items-center justify-between mt-4">
          <p className="text-xs font-body text-navy/50">
            {t('auth.noAccount')}{' '}
            <Link to="/register" className="text-cyan hover:underline">
              {t('auth.signUp')}
            </Link>
          </p>
          <span className="font-mono text-xs text-navy/20">v{APP_VERSION}</span>
        </div>
      </div>
    </div>
  )
}
