import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  me,
  nostrChallenge,
  nostrSignup,
  nostrVerify,
  type NostrProof,
} from '../api/auth'
import { PURPOSE_LOGIN, PURPOSE_SIGNUP } from '../lib/identity'
import { hasNip07Extension } from '../lib/nostr'
import { useAuthStore } from '../stores/auth'

/** T3.13 — sign in or sign up with a Nostr key, no password anywhere.
 *
 *  The private key never leaves the extension: we ask it to sign a challenge
 *  the server issued and send back only the signature. The purpose string is
 *  part of what gets signed, so a signature gathered for login cannot be
 *  replayed to create an account.
 */
interface Props {
  mode: 'login' | 'signup'
  /** Required in signup mode — the account has no other name to go by. */
  displayName?: string
}

export default function NostrAuthButton({ mode, displayName }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const available = hasNip07Extension()

  const finish = (token: string) => {
    localStorage.setItem('token', token)
    return me().then(({ data: user }) => {
      setAuth(user, token)
      navigate(user.email && !user.email_verified ? '/verify-email' : '/dashboard')
    })
  }

  const run = async () => {
    setBusy(true)
    setError('')
    try {
      if (!window.nostr) {
        setError(t('nostrAuth.noExtension') as string)
        return
      }
      const pubkey = await window.nostr.getPublicKey()
      const { data: ch } = await nostrChallenge(pubkey)
      const purpose = mode === 'signup' ? PURPOSE_SIGNUP : PURPOSE_LOGIN

      const signed = await window.nostr.signEvent({
        kind: 27235,
        created_at: Math.floor(Date.now() / 1000),
        tags: [
          ['challenge', ch.challenge],
          ['purpose', purpose],
        ],
        content: purpose,
      })
      const proof: NostrProof = {
        npub_hex: signed.pubkey,
        challenge: ch.challenge,
        created_at: signed.created_at,
        sig: signed.sig,
      }

      if (mode === 'signup') {
        const name = (displayName ?? '').trim()
        if (!name) {
          setError(t('nostrAuth.needName') as string)
          return
        }
        const { data } = await nostrSignup({ ...proof, display_name: name })
        await finish(data.token.access_token)
        return
      }

      const { data } = await nostrVerify(proof)
      await finish(data.access_token)
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number } })?.response
      if (resp?.status === 404) {
        // Not a failed login — this key simply has no account here yet.
        setError(t('nostrAuth.unknownKey') as string)
      } else if (resp?.status === 409) {
        setError(t('nostrAuth.alreadyRegistered') as string)
      } else if (resp?.status === 403) {
        setError(t('nostrAuth.retired') as string)
      } else if (resp?.status === 401) {
        setError(t('nostrAuth.badProof') as string)
      } else {
        setError(t('common.errorGeneric') as string)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={run}
        disabled={!available || busy}
        data-testid={`nostr-auth-${mode}`}
        className="w-full border border-navy/20 rounded-field py-2.5 text-sm font-body text-navy disabled:opacity-40 transition-opacity"
      >
        {busy
          ? '…'
          : available
            ? t(mode === 'signup' ? 'nostrAuth.signupCta' : 'nostrAuth.loginCta')
            : t('nostrAuth.noExtension')}
      </button>
      {!available && (
        <p className="text-xs font-body text-muted">
          {/* Naming a way forward beats a dead end — most people hitting this
              have never heard of NIP-07. */}
          {t('nostrAuth.noExtensionHint')}
        </p>
      )}
      {error && (
        <div className="bg-amber/10 border border-amber/40 rounded-field px-3 py-2">
          <p className="text-sm font-body text-navy">{error}</p>
        </div>
      )}
    </div>
  )
}
