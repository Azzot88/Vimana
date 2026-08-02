import { useState } from 'react'
import { createInvite, type Invite } from '../api/social'
import MonoText from '../components/MonoText'

export default function InvitePage() {
  const [invite, setInvite] = useState<Invite | null>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  const inviteUrl = invite
    ? `${window.location.origin}/invite/${invite.token}`
    : null

  const handleCreate = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await createInvite()
      setInvite(data)
    } catch {
      setError('Не удалось создать ссылку')
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
      <h1 className="font-display font-bold text-2xl text-navy">Пригласить контакт</h1>

      <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
        <p className="text-sm font-body text-navy/60">
          Создайте персональную ссылку-приглашение. После перехода по ней пользователь будет добавлен в ваши контакты.
        </p>

        {!invite ? (
          <>
            {error && <p className="text-xs font-mono text-amber">{error}</p>}
            <button
              onClick={handleCreate}
              disabled={loading}
              className="bg-navy text-ivory font-display font-medium px-5 py-2.5 rounded-field text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
            >
              {loading ? 'Создание...' : 'Создать ссылку'}
            </button>
          </>
        ) : (
          <div className="space-y-3">
            <div className="bg-ivory rounded-field p-3 border border-navy/10">
              <MonoText className="text-xs text-navy/70 break-all">{inviteUrl}</MonoText>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleCopy}
                className="bg-cyan text-white font-display font-medium px-4 py-2 rounded-field text-sm hover:opacity-90 transition-opacity"
              >
                {copied ? 'Скопировано ✓' : 'Скопировать'}
              </button>
              <button
                onClick={() => { setInvite(null); setCopied(false) }}
                className="text-sm font-body text-navy/40 hover:text-navy transition-colors px-3"
              >
                Создать ещё
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
