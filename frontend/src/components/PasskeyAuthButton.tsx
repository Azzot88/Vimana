import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  browserSupportsWebAuthn,
  startAuthentication,
  startRegistration,
} from '@simplewebauthn/browser'
import { me } from '../api/auth'
import {
  passkeyLoginOptions,
  passkeyLoginVerify,
  passkeySignupOptions,
  passkeySignupVerify,
} from '../api/passkey'
import { useAuthStore } from '../stores/auth'

/** T3.14 — sign in or sign up with a passkey.
 *
 *  The private key never leaves the authenticator; the browser signs a
 *  challenge and we forward the answer. Nothing here can be phished the way a
 *  password can — the credential is bound to this origin by the platform.
 */
interface Props {
  mode: 'login' | 'signup'
  /** Required in signup mode — a passkey account may have no email, so this is
   *  the only name it would otherwise have. */
  displayName?: string
  email?: string
}

export default function PasskeyAuthButton({ mode, displayName, email }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [supported, setSupported] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setSupported(browserSupportsWebAuthn())
  }, [])

  const finish = async (token: string) => {
    localStorage.setItem('token', token)
    const { data: user } = await me()
    setAuth(user, token)
    navigate(user.email && !user.email_verified ? '/verify-email' : '/dashboard')
  }

  const run = async () => {
    setBusy(true)
    setError('')
    try {
      if (mode === 'signup') {
        const name = (displayName ?? '').trim()
        if (!name) {
          setError(t('passkey.needName') as string)
          return
        }
        const { data: opts } = await passkeySignupOptions({
          display_name: name,
          email: email?.trim() || undefined,
        })
        const credential = await startRegistration({
          optionsJSON: opts.options as never,
        })
        const { data } = await passkeySignupVerify({
          ceremony_id: opts.ceremony_id,
          credential,
          device_name: guessDeviceName(),
        })
        await finish(data.token.access_token)
        return
      }

      const { data: opts } = await passkeyLoginOptions()
      const credential = await startAuthentication({
        optionsJSON: opts.options as never,
      })
      const { data } = await passkeyLoginVerify({
        ceremony_id: opts.ceremony_id,
        credential,
      })
      await finish(data.access_token)
    } catch (err: unknown) {
      setError(describeError(err, t))
    } finally {
      setBusy(false)
    }
  }

  if (!supported) {
    return (
      <p className="text-xs font-body text-muted">
        {t('passkey.unsupported')}
      </p>
    )
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={run}
        disabled={busy}
        data-testid={`passkey-${mode}`}
        className="w-full border border-navy/20 rounded-field py-2.5 text-sm font-body text-navy disabled:opacity-40 transition-opacity"
      >
        {busy
          ? '…'
          : t(mode === 'signup' ? 'passkey.signupCta' : 'passkey.loginCta')}
      </button>
      {error && (
        <div className="bg-amber/10 border border-amber/40 rounded-field px-3 py-2">
          <p className="text-sm font-body text-navy">{error}</p>
        </div>
      )}
    </div>
  )
}

/** Best-effort label so the device list is not a row of blanks. The user can
 *  rename it later; guessing beats an empty string. */
export function guessDeviceName(): string {
  const ua = navigator.userAgent
  if (/iPhone|iPad/.test(ua)) return 'iPhone'
  if (/Android/.test(ua)) return 'Android'
  if (/Macintosh/.test(ua)) return 'Mac'
  if (/Windows/.test(ua)) return 'Windows'
  return 'This device'
}

function describeError(err: unknown, t: (k: string) => unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const name = (err as { name?: string })?.name

  // The user dismissed the platform prompt, or no credential matched. Not a
  // failure worth an alarming message — they simply changed their mind.
  if (name === 'NotAllowedError' || name === 'AbortError') {
    return t('passkey.cancelled') as string
  }
  if (status === 409) return t('passkey.alreadyRegistered') as string
  if (status === 403) return t('passkey.retired') as string
  if (status === 401) return t('passkey.failed') as string
  return t('common.errorGeneric') as string
}
