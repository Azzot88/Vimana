import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { startAuthentication } from '@simplewebauthn/browser'
import {
  stepUpOptions,
  stepUpVerify,
  type StepUpMethod,
  type StepUpOptions,
  type StepUpScope,
} from '../api/stepUp'

/**
 * T3.15 — asks the user to prove they are still here, before something
 * irreversible happens.
 *
 * The available proofs come from the server rather than from a guess: an
 * account with no password must never be shown a password prompt, and an
 * account whose key is already retired cannot sign. Offering a method that
 * cannot succeed is worse than offering none.
 */
interface Props {
  scope: StepUpScope
  title: string
  body: string
  onConfirm: (token: string) => void | Promise<void>
  onCancel: () => void
}

export default function StepUpDialog({
  scope,
  title,
  body,
  onConfirm,
  onCancel,
}: Props) {
  const { t } = useTranslation()
  const [options, setOptions] = useState<StepUpOptions | null>(null)
  const [method, setMethod] = useState<StepUpMethod | null>(null)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    stepUpOptions(scope)
      .then(({ data }) => {
        if (cancelled) return
        setOptions(data)
        setMethod(data.methods[0] ?? null)
      })
      .catch(() => {
        if (!cancelled) setError(t('stepUp.errorLoad') as string)
      })
    return () => {
      cancelled = true
    }
  }, [scope, t])

  const submit = async () => {
    if (!options || !method) return
    setBusy(true)
    setError('')
    try {
      let payload: Parameters<typeof stepUpVerify>[0] = { scope }

      if (method === 'password') {
        payload = { scope, password }
      } else if (method === 'passkey') {
        if (!options.webauthn) throw new Error('no webauthn options')
        const credential = await startAuthentication({
          optionsJSON: options.webauthn as never,
        })
        payload = { scope, webauthn: credential as never }
      } else {
        if (!window.nostr || !options.challenge) {
          setError(t('stepUp.errorNoExtension') as string)
          return
        }
        const createdAt = Math.floor(Date.now() / 1000)
        const signed = await window.nostr.signEvent({
          kind: 27235,
          created_at: createdAt,
          tags: [
            ['challenge', options.challenge],
            ['purpose', options.purpose],
          ],
          content: options.purpose,
        })
        payload = {
          scope,
          nostr: {
            npub_hex: signed.pubkey,
            challenge: options.challenge,
            created_at: signed.created_at,
            sig: signed.sig,
          },
        }
      }

      const { data } = await stepUpVerify(payload)
      await onConfirm(data.step_up_token)
    } catch (err: unknown) {
      const name = (err as { name?: string })?.name
      if (name === 'NotAllowedError' || name === 'AbortError') {
        setError(t('stepUp.cancelled') as string)
      } else {
        setError(t('stepUp.errorFailed') as string)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-navy/40 flex items-center justify-center px-4 z-modal">
      <div className="bg-white rounded-card border border-navy/10 p-5 w-full max-w-sm space-y-4">
        <h3 className="font-display font-semibold text-lg text-navy">{title}</h3>
        <p className="text-sm font-body text-muted">{body}</p>

        {options && options.methods.length > 1 && (
          <div className="flex gap-2 flex-wrap">
            {options.methods.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMethod(m)}
                className={`text-xs font-body px-2.5 py-1 rounded border transition-colors ${
                  method === m
                    ? 'border-cyan text-link bg-cyan/5'
                    : 'border-navy/20 text-muted'
                }`}
              >
                {t(`stepUp.method.${m}`)}
              </button>
            ))}
          </div>
        )}

        {method === 'password' && (
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('stepUp.passwordPlaceholder') as string}
            autoFocus
            className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
          />
        )}
        {method === 'passkey' && (
          <p className="text-sm font-body text-muted">{t('stepUp.passkeyHint')}</p>
        )}
        {method === 'nostr' && (
          <p className="text-sm font-body text-muted">{t('stepUp.nostrHint')}</p>
        )}

        {error && (
          <div className="bg-amber/10 border border-amber/40 rounded-field px-3 py-2">
            <p className="text-sm font-body text-navy">{error}</p>
          </div>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 border border-navy/20 rounded-field py-2 text-sm font-body text-navy"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={
              busy ||
              !method ||
              (method === 'password' && !password)
            }
            data-testid="step-up-confirm"
            className="flex-1 bg-navy text-ivory rounded-field py-2 text-sm font-body font-medium disabled:opacity-40"
          >
            {busy ? '…' : t('stepUp.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}
