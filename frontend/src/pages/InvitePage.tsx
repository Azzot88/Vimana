import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { createInvite, type Invite } from '../api/social'
import MonoText from '../components/MonoText'

/**
 * T_UX.7 pt.3 — translated. Every string here was Russian in the source.
 *
 * One constraint that is not visible from this file: `e2e/specs/invite-flow`
 * finds the create button by an accessible-name regex spanning all six locales
 * (`создать ссылку|create link|створити|utwórz|créer|crear`). The translations
 * keep those substrings, so the labels are not free text — see the freeze list
 * in `TASKS.md` `T_UX.7` before rewording them.
 */
export default function InvitePage() {
  const { t } = useTranslation()
  const [invite, setInvite] = useState<Invite | null>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  const inviteUrl = invite ? `${window.location.origin}/invite/${invite.token}` : null

  const handleCreate = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await createInvite()
      setInvite(data)
    } catch {
      setError(t('invite.createFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = async () => {
    if (!inviteUrl) return
    try {
      await navigator.clipboard.writeText(inviteUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // `navigator.clipboard` needs a secure context and a user gesture; on
      // older mobile browsers it is simply absent. The fallback is ugly and it
      // works, which beats a copy button that silently does nothing.
      const el = document.createElement('textarea')
      el.value = inviteUrl
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="max-w-md space-y-6">
      <h1 className="font-display font-bold text-2xl text-navy">{t('invite.title')}</h1>

      <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
        <p className="text-sm font-body text-navy/60">{t('invite.hint')}</p>

        {!invite ? (
          <>
            {/* A failed action is `danger`, not `amber`: amber means "look
                here", red means "this did not happen". */}
            {error && <p className="text-xs font-mono text-danger">{error}</p>}
            <button
              type="button"
              onClick={handleCreate}
              disabled={loading}
              className="bg-navy text-ivory font-display font-medium px-5 py-2.5 rounded-field text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
            >
              {loading ? t('common.sending') : t('invite.create')}
            </button>
          </>
        ) : (
          <div className="space-y-3">
            <div className="bg-ivory rounded-field p-3 border border-navy/10">
              <MonoText className="text-xs text-navy/70 break-anywhere">{inviteUrl}</MonoText>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCopy}
                className="bg-cyan text-white font-display font-medium px-4 py-2 rounded-field text-sm hover:opacity-90 transition-opacity"
              >
                {copied ? t('common.copied') : t('profile.inviteCopy')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setInvite(null)
                  setCopied(false)
                }}
                className="text-sm font-body text-navy/40 hover:text-navy transition-colors px-3"
              >
                {t('invite.createAnother')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
