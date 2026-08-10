import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  changePassword,
  consumeRecoveryCode,
  forgotPassword,
  login,
  loginMethods,
  me,
} from '../api/auth'
import NostrAuthButton from '../components/NostrAuthButton'
import PasskeyAuthButton from '../components/PasskeyAuthButton'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { useAuthStore } from '../stores/auth'
import { usePersistedState } from '../hooks/usePersistedState'
import { APP_VERSION } from '../version'

/**
 * T_UX.7 pt.2 — where to go after signing in.
 *
 * `AcceptInvitePage` has always sent people here as `/login?returnUrl=/invite/…`
 * and nothing ever read the parameter, so anyone opening an invite link while
 * signed out landed on the dashboard and the invite was silently dropped. The
 * person who sent it never got connected and had no way to know.
 *
 * Reading it back is also the exact sink the react-router open-redirect
 * advisory (GHSA-wrjc-x8rr-h8h6) is about, so the check is deliberately narrow
 * rather than clever: one leading slash, no scheme, no protocol-relative `//`,
 * no backslash — which browsers normalise to `/` and which is what that
 * advisory turns into an off-site redirect. Anything else falls back to `/`,
 * because a login that lands somewhere harmless is a nuisance and one that
 * lands on an attacker's page is a phishing step.
 */
export function safeReturnUrl(raw: string | null): string {
  if (!raw) return '/'
  if (!raw.startsWith('/')) return '/'
  if (raw.startsWith('//') || raw.startsWith('/\\')) return '/'
  if (raw.includes('\\')) return '/'
  return raw
}

export default function LoginPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const inactivityLogout = searchParams.get('reason') === 'inactivity'
  const returnUrl = safeReturnUrl(searchParams.get('returnUrl'))
  const setAuth = useAuthStore((s) => s.setAuth)
  const [loginVal, setLoginVal] = usePersistedState<string>('login:login', '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  /** T3.16 — recovery lives on the login screen because that is where a
   *  locked-out person already is. Sending them hunting for a separate page is
   *  the worst moment to ask for navigation. */
  const [recovering, setRecovering] = useState(false)
  const [recoveryCode, setRecoveryCode] = useState('')
  const [recoveryPassword, setRecoveryPassword] = useState('')
  // T_SEC.5 — asked once the identifier looks complete, so the screen offers
  // what this account can actually do instead of a fixed menu.
  const [methods, setMethods] = useState<string[] | null>(null)
  const [canReset, setCanReset] = useState(false)
  const [resetSent, setResetSent] = useState(false)

  const handleRecovery = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data: session } = await consumeRecoveryCode(loginVal, recoveryCode)
      // The recovery token is not a session — `/me` refuses it. It is stored
      // only so the password call below carries it, and is replaced a moment
      // later by the real one that call returns.
      localStorage.setItem('token', session.access_token)
      const { data } = await changePassword(
        recoveryPassword,
        session.step_up_tokens.change_password,
      )
      localStorage.setItem('token', data.access_token)
      const { data: user } = await me()
      setAuth(user, data.access_token)
      navigate(returnUrl)
    } catch {
      // Deliberately one message: the server answers the same 401 for a wrong
      // code and an unknown account, and the UI must not undo that.
      setError(t('auth.recoveryFailed'))
      localStorage.removeItem('token')
    } finally {
      setLoading(false)
    }
  }

  // Debounced so typing an address is not a request per keystroke, and only
  // for something that already looks like one — the endpoint is rate-limited
  // and an incomplete identifier tells it nothing anyway.
  useEffect(() => {
    const value = loginVal.trim()
    setResetSent(false)
    if (!value.includes('@') || value.length < 6) {
      setMethods(null)
      setCanReset(false)
      return
    }
    const timer = setTimeout(() => {
      loginMethods(value)
        .then(({ data }) => {
          setMethods(data.methods)
          setCanReset(data.can_reset)
        })
        .catch(() => {})
    }, 500)
    return () => clearTimeout(timer)
  }, [loginVal])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data: tokenData } = await login({ login: loginVal, password })
      localStorage.setItem('token', tokenData.access_token)
      const { data: user } = await me()
      setAuth(user, tokenData.access_token)
      navigate(returnUrl)
    } catch {
      setError(t('auth.errorCredentials'))
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
        {inactivityLogout && (
          <div className="bg-amber/10 border border-amber/40 rounded-field px-4 py-3 mb-4">
            <p className="text-sm font-body text-navy">
              {t('auth.inactivityLoggedOut')}
            </p>
          </div>
        )}
        <form
          onSubmit={recovering ? handleRecovery : handleSubmit}
          className="bg-white rounded-card border border-navy/10 p-6 space-y-4"
        >
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              {recovering ? t('auth.recoveryIdentifier') : t('auth.email')}
            </label>
            <input
              /* Not `type="email"` in recovery: the identifier may be an npub,
                 and the browser would refuse to submit it. */
              type={recovering ? 'text' : 'email'}
              value={loginVal}
              onChange={(e) => setLoginVal(e.target.value)}
              required
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="user@example.com"
            />
          </div>
          {recovering ? (
            <>
              <div>
                <label className="block text-xs font-body font-medium text-navy/60 mb-1">
                  {t('auth.recoveryCode')}
                </label>
                <input
                  type="text"
                  value={recoveryCode}
                  onChange={(e) => setRecoveryCode(e.target.value)}
                  required
                  autoCapitalize="characters"
                  autoCorrect="off"
                  spellCheck={false}
                  data-testid="recovery-code-input"
                  className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
                  placeholder="XXXX-XXXX-XXXX"
                />
              </div>
              <div>
                <label className="block text-xs font-body font-medium text-navy/60 mb-1">
                  {t('auth.recoveryNewPassword')}
                </label>
                <input
                  type="password"
                  value={recoveryPassword}
                  onChange={(e) => setRecoveryPassword(e.target.value)}
                  required
                  minLength={8}
                  className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
                  placeholder="••••••••"
                />
              </div>
              <p className="text-xs font-body text-navy/50">
                {t('auth.recoveryNotice')}
              </p>
            </>
          ) : (
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
          )}
          {error && (
            <p className="text-xs font-mono text-amber">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-navy text-ivory font-display font-medium py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
          >
            {loading
              ? t('auth.logging')
              : recovering
                ? t('auth.recoverySubmit')
                : t('auth.login')}
          </button>
          <button
            type="button"
            onClick={() => {
              setRecovering(!recovering)
              setError('')
            }}
            data-testid="recovery-toggle"
            hidden={methods !== null && !methods.includes('recovery_code') && !recovering}
            className="w-full text-xs font-body text-navy/50"
          >
            {recovering ? t('auth.recoveryBack') : t('auth.recoveryStart')}
          </button>
        </form>

        {/* T_SEC.5 — the way back that the overwhelming majority actually has.
            Until now the only one offered was a recovery code, which almost
            nobody has ever created: the screen answered "prove it with the
            thing you never made" to a situation the product created. Shown
            only once the identifier is known to have a password and a verified
            address — offering a reset to a passkey account is the same mistake
            in the other direction. */}
        {!recovering && canReset && (
          <div className="mt-3">
            {resetSent ? (
              <p
                data-testid="reset-sent"
                className="bg-cyan/10 border border-cyan/30 rounded-field px-3 py-2 text-xs font-body text-navy"
              >
                {t('auth.resetSent')}
              </p>
            ) : (
              <button
                type="button"
                data-testid="forgot-password"
                onClick={async () => {
                  try {
                    await forgotPassword(loginVal.trim())
                  } catch { /* the answer is 202 either way */ }
                  setResetSent(true)
                }}
                className="w-full text-xs font-body text-link underline underline-offset-2"
              >
                {t('auth.forgotPassword')}
              </button>
            )}
          </div>
        )}
        <div className="mt-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="h-px bg-navy/10 flex-1" />
            <span className="text-xs font-body text-navy/40">
              {t('nostrAuth.or')}
            </span>
            <div className="h-px bg-navy/10 flex-1" />
          </div>
          <div className="space-y-2">
            <PasskeyAuthButton mode="login" />
            <NostrAuthButton mode="login" />
          </div>
        </div>
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
