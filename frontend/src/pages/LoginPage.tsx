import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  changePassword,
  consumeRecoveryCode,
  contactChannels,
  forgotPassword,
  login,
  loginMethods,
  me,
  otpRequest,
  otpVerify,
} from '../api/auth'
import NostrAuthButton from '../components/NostrAuthButton'
import PasskeyAuthButton from '../components/PasskeyAuthButton'
import CodeField from '../components/CodeField'
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
  const { t, i18n } = useTranslation()
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
  /**
   * T3.28 pt.2 — the one-field door.
   *
   * `channels` is what this identifier can be *proved* through; `stage` is
   * where in the exchange we are. The password block below is not removed and
   * not hidden behind a link: accounts created before this flow have one, and
   * a screen that quietly stops offering the thing somebody has used for
   * months reads as a broken site, not as a new feature.
   */
  const [channels, setChannels] = useState<string[]>([])
  /** T3.27 — set once a Telegram link has been handed out. It replaces the
   *  identifier when the code comes back: there was never an address. */
  const [telegramNonce, setTelegramNonce] = useState('')
  /** Channels usable with nothing typed at all. Asked once, on load — the
   *  screen must not decide on its own whether our bot exists. */
  const [openChannels, setOpenChannels] = useState<string[]>([])
  const [stage, setStage] = useState<'identify' | 'code'>('identify')
  const [code, setCode] = useState('')
  const [sentVia, setSentVia] = useState('')
  // Shape only, and deliberately loose: this decides whether to explain
  // something, not whether to accept anything. The server owns validity.
  const looksLikePhone =
    !loginVal.includes('@') && /^[+\d][\d\s()-]{6,}$/.test(loginVal.trim())

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

  // T3.27 — asked once, with nothing typed: which channels work without an
  // identifier at all. Today that is Telegram, and only where a bot is
  // configured. A button hardcoded here would be a button that quietly does
  // nothing on a deployment without one.
  useEffect(() => {
    contactChannels('')
      .then(({ data }) => setOpenChannels(data.channels))
      .catch(() => setOpenChannels([]))
  }, [])

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
      // Asked about the identifier, never about the account — an email offers
      // email, a phone offers whatever reaches the number. Both answers are
      // the same for a stranger and for a member, by construction.
      contactChannels(value)
        .then(({ data }) => setChannels(data.channels))
        .catch(() => setChannels([]))
    }, 500)
    return () => clearTimeout(timer)
  }, [loginVal])

  /**
   * T3.27 — Telegram, which runs backwards.
   *
   * Every other channel is told an address and delivers. A bot cannot write to
   * somebody who has never written to it, so this hands back a link, the person
   * opens the chat, and the code arrives there. The nonce stands in for the
   * identifier from then on: they named nothing, and the account is resolved
   * from the chat they proved.
   */
  const startTelegram = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await otpRequest('', 'telegram', i18n.language)
      if (!data.link || !data.nonce) throw new Error('no link')
      setTelegramNonce(data.nonce)
      setSentVia('telegram')
      setStage('code')
      // A new tab, not a redirect: the code screen has to survive the trip to
      // Telegram and back, and on desktop the app takes the link without the
      // browser going anywhere at all.
      window.open(data.link, '_blank')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setError(status === 503 ? t('auth.telegramUnavailable') : t('auth.errorServer'))
    } finally {
      setLoading(false)
    }
  }

  const sendCode = async (channel: string) => {
    if (channel === 'telegram') return startTelegram()
    setLoading(true)
    setError('')
    try {
      await otpRequest(loginVal.trim(), channel, i18n.language)
      setSentVia(channel)
      setStage('code')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      // 429 is the only status this endpoint answers differently, and it is
      // about the caller's own last request — so it is the only one worth
      // repeating back.
      setError(status === 429 ? t('auth.codeCooldown') : t('auth.errorServer'))
    } finally {
      setLoading(false)
    }
  }

  const submitCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      // T3.27 — for Telegram the nonce *is* the identifier: the person typed no
      // address, and the exchange is what the code belongs to.
      const { data } = telegramNonce
        ? await otpVerify(telegramNonce, code.trim(), undefined, 'telegram')
        : await otpVerify(loginVal.trim(), code.trim(), password)
      localStorage.setItem('token', data.access_token)
      const { data: user } = await me()
      setAuth(user, data.access_token)
      // The server says whether it just made this account. It used to be
      // guessed by comparing the display name with the local part of the
      // address — a guess that cannot work at all for an account born in a chat.
      navigate(data.created ? '/welcome' : returnUrl)
    } catch {
      // One message for wrong, expired and already-spent: the server does not
      // tell them apart either, and separating them helps whoever is guessing.
      setError(t('auth.codeFailed'))
    } finally {
      setLoading(false)
    }
  }

  /**
   * T3.28 pt.4 — one button, two possible lives.
   *
   * With a password typed, this tries to sign in. A 401 does **not** mean
   * "wrong password": the server answers the same for a wrong password and for
   * an address nobody has registered, on purpose, and asking it to tell them
   * apart would hand a stranger a way to enumerate accounts. So the fallback
   * covers both readings at once — a code goes to the address, and whichever
   * of the two situations it was, the code resolves it: it lets a forgetful
   * owner in, or it creates the account and applies the password they just
   * typed.
   *
   * With no password, it goes straight to the code. Same button, same two
   * steps, and the screen never has to know which kind of person is using it.
   */
  const handleOneDoor = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!password) {
      await sendCode(channels[0] ?? 'email')
      return
    }
    setLoading(true)
    setError('')
    try {
      const { data: tokenData } = await login({ login: loginVal.trim(), password })
      localStorage.setItem('token', tokenData.access_token)
      const { data: user } = await me()
      setAuth(user, tokenData.access_token)
      navigate(returnUrl)
    } catch {
      setLoading(false)
      await sendCode(channels[0] ?? 'email')
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
        {/* T3.28 pt.2 fix (2026-08-10) — one card, not three stacked blocks.
            The code entry was rendered after this form and outside it: full
            width, its own border, its own button, sitting on the page instead
            of in the card. Next to the password field it read as a different
            product. Everything that is "how you get in" now lives in one
            container and reuses the same field and the same button. */}
        <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
        <form
          onSubmit={recovering ? handleRecovery : handleOneDoor}
          className="space-y-4"
        >
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              {recovering ? t('auth.recoveryIdentifier') : t('auth.email')}
              {!recovering && <span className="text-amber"> *</span>}
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
                {t('auth.passwordOptional')}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
                placeholder="••••••••"
              />
              <p className="text-[11px] font-body text-muted mt-1">
                {t('auth.passwordLater')}
              </p>
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
                : t('auth.enter')}
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
          <div>
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
        {/* T3.28 pt.2 — the code path, above the password because it is the one
            that works for everybody: an account that has never chosen a
            password still has an address, and a visitor with no account at all
            gets one from the same two steps. */}
        {/* T3.30 (2026-08-10) — a phone can be proved by nothing now, so it
            gets an explanation rather than a button that quietly does nothing.
            The screen knowing this is the whole reason `/contact/channels`
            answers about the identifier instead of the account. */}
        {!recovering && stage === 'identify' && looksLikePhone && (
          <p
            data-testid="phone-not-a-login"
            className="text-xs font-body text-muted border-t border-navy/10 pt-4"
          >
            {t('auth.phoneNotALogin')}
          </p>
        )}

        {/* Only when there is a real choice. An email address has exactly one
            channel, so a picker there would be a button that asks a question
            with one answer — the single submit above already sends it. */}
        {!recovering && stage === 'identify' && channels.length > 1 && (
          <div className="space-y-2 border-t border-navy/10 pt-4" data-testid="code-channels">
            <p className="text-xs font-body text-muted">{t('auth.codeHint')}</p>
            <div className="flex flex-wrap gap-2">
              {channels.map((channel) => (
                <button
                  key={channel}
                  type="button"
                  disabled={loading}
                  onClick={() => sendCode(channel)}
                  data-testid={`send-code-${channel}`}
                  className="flex-1 min-w-[8rem] border border-cyan/40 bg-cyan/5 rounded-field py-2 text-sm font-body text-navy disabled:opacity-40"
                >
                  {t(`auth.channel.${channel}`)}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* T3.27 — a way in that needs nothing typed. Placed after the picker
            because it is a different kind of act: not "send my code there" but
            "I have no address to give you". */}
        {!recovering && stage === 'identify' && openChannels.includes('telegram') && (
          <div className="border-t border-navy/10 pt-4">
            <button
              type="button"
              disabled={loading}
              onClick={startTelegram}
              data-testid="login-telegram"
              className="w-full border border-cyan/40 bg-cyan/5 rounded-field py-2.5 text-sm font-body text-navy disabled:opacity-40"
            >
              {t('auth.telegramLogin')}
            </button>
          </div>
        )}

        {!recovering && stage === 'code' && (
          <form onSubmit={submitCode} className="space-y-3 border-t border-navy/10 pt-4" data-testid="code-form">
            <p className="text-xs font-body text-muted">
              {t('auth.codeSent', { channel: t(`auth.channel.${sentVia}`) })}
            </p>
            <CodeField
              id="otp-code"
              value={code}
              onChange={setCode}
              autoFocus
              data-testid="otp-code-input"
            />
            <button
              type="submit"
              disabled={loading || code.trim().length < 6}
              className="w-full bg-navy text-ivory font-display font-medium py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
            >
              {loading ? t('auth.logging') : t('auth.codeSubmit')}
            </button>
            <button
              type="button"
              onClick={() => {
                setStage('identify')
                setCode('')
                setError('')
                // T3.27 — the nonce belongs to the exchange being abandoned.
                // Kept, it would be spent against the next code typed here,
                // which belongs to a different one entirely.
                setTelegramNonce('')
              }}
              className="w-full text-xs font-body text-muted"
            >
              {t('auth.codeBack')}
            </button>
          </form>
        )}

        </div>

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
          <p className="text-xs font-body text-muted max-w-[16rem]">
            {/* T3.28 pt.3 — there is no separate sign-up any more, so there is
                nothing to link to. Saying so is better than a link that lands
                on the page you are already reading. */}
            {t('auth.noAccountHint')}
          </p>
          <span className="font-mono text-xs text-navy/20">v{APP_VERSION}</span>
        </div>
      </div>
    </div>
  )
}
