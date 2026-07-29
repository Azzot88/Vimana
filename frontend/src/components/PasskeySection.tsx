import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  browserSupportsWebAuthn,
  startRegistration,
} from '@simplewebauthn/browser'
import {
  deletePasskey,
  listPasskeys,
  passkeyRegisterOptions,
  passkeyRegisterVerify,
  type PasskeyCredential,
} from '../api/passkey'
import { guessDeviceName } from './PasskeyAuthButton'
import StepUpDialog from './StepUpDialog'

/** T3.14 — the account's sign-in devices.
 *
 *  Each row is a device, not an identity: removing one leaves `nostr_pubkey`
 *  and every other device untouched. That is the point of passkeys here —
 *  losing a phone stops being an account-level event.
 */
export default function PasskeySection() {
  const { t } = useTranslation()
  const [items, setItems] = useState<PasskeyCredential[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pendingRemoval, setPendingRemoval] = useState<string | null>(null)

  const supported = browserSupportsWebAuthn()

  const load = async () => {
    try {
      const { data } = await listPasskeys()
      setItems(data)
      setError('')
    } catch {
      // Not silently empty. The first version swallowed this and rendered
      // "no devices yet" for a *failed* request — which is what a broken
      // redirect looked like for an hour: a device was registered, the list
      // call died, and the UI calmly reported nothing was there.
      setItems([])
      setError(t('passkey.loadFailed') as string)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const add = async () => {
    setBusy(true)
    setError('')
    try {
      const { data: opts } = await passkeyRegisterOptions()
      const credential = await startRegistration({
        optionsJSON: opts.options as never,
      })
      await passkeyRegisterVerify({
        ceremony_id: opts.ceremony_id,
        credential,
        device_name: guessDeviceName(),
      })
      await load()
    } catch (err: unknown) {
      const name = (err as { name?: string })?.name
      const status = (err as { response?: { status?: number } })?.response?.status
      if (name === 'NotAllowedError' || name === 'AbortError') {
        setError(t('passkey.cancelled') as string)
      } else if (status === 409) {
        setError(t('passkey.deviceAlreadyAdded') as string)
      } else {
        setError(t('common.errorGeneric') as string)
      }
    } finally {
      setBusy(false)
    }
  }

  /** T3.15 — unlinking needs a fresh confirmation: dropping every device but
   *  their own is how someone with a stolen session would lock the owner out. */
  const remove = async (id: string, token: string) => {
    setError('')
    setPendingRemoval(null)
    try {
      await deletePasskey(id, token)
      await load()
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      // 409 is the lock-out guard: this is the account's last door.
      setError(
        (status === 409
          ? t('passkey.lastWayIn')
          : t('common.errorGeneric')) as string,
      )
    }
  }

  if (items === null) return null

  return (
    <div className="bg-white rounded-2xl border border-navy/10 p-5 space-y-4">
      <h2 className="font-display font-semibold text-lg text-navy">
        {t('passkey.sectionTitle')}
      </h2>
      <p className="text-sm font-body text-navy/60">{t('passkey.sectionHint')}</p>

      {error && (
        <div className="bg-amber/10 border border-amber/40 rounded-lg px-3 py-2">
          <p className="text-sm font-body text-navy">{error}</p>
        </div>
      )}

      {items.length === 0 ? (
        <p className="text-sm font-body text-navy/50">{t('passkey.empty')}</p>
      ) : (
        <ul className="space-y-2" data-testid="passkey-list">
          {items.map((c) => (
            <li
              key={c.id}
              className="flex items-center justify-between gap-3 border border-navy/10 rounded-lg px-3 py-2"
            >
              <div className="min-w-0">
                <div className="text-sm font-body text-navy truncate">
                  {c.device_name || t('passkey.unnamedDevice')}
                </div>
                <div className="text-xs font-body text-navy/50">
                  {t(`passkey.kind.${c.device_kind}`)}
                  {c.last_used_at
                    ? ` · ${t('passkey.lastUsed')} ${new Date(
                        c.last_used_at,
                      ).toLocaleDateString()}`
                    : ''}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setPendingRemoval(c.id)}
                className="text-xs font-body text-navy/50 hover:text-navy shrink-0"
              >
                {t('passkey.remove')}
              </button>
            </li>
          ))}
        </ul>
      )}

      {supported ? (
        <button
          type="button"
          onClick={add}
          disabled={busy}
          data-testid="passkey-add"
          className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy disabled:opacity-40"
        >
          {busy ? '…' : t('passkey.addCta')}
        </button>
      ) : (
        <p className="text-xs font-body text-navy/50">
          {t('passkey.unsupported')}
        </p>
      )}

      {pendingRemoval && (
        <StepUpDialog
          scope="unlink_passkey"
          title={t('passkey.remove') as string}
          body={t('passkey.removeConfirm') as string}
          onConfirm={(token) => remove(pendingRemoval, token)}
          onCancel={() => setPendingRemoval(null)}
        />
      )}
    </div>
  )
}
