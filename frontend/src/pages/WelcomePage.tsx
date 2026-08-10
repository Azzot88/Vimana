import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { me, updateMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import LanguageSwitcher from '../components/LanguageSwitcher'

/**
 * T3.28 pt.2 — the one question left after a code created an account.
 *
 * The name is asked *here* rather than on the sign-in form, and that ordering
 * is the point. Asking before the code would mean collecting something from
 * every visitor including the ones who only wanted to sign in; asking during
 * would mean refusing to finish without it, which would burn the code they had
 * just spent correctly. So the account is created with the local part of their
 * address as a placeholder and renamed here, once, while they are already
 * looking at the screen.
 *
 * Skippable on purpose. The placeholder is serviceable, the person can rename
 * themselves later in the profile, and a wall between someone and the product
 * they just proved they wanted is a strange thing to build.
 */
export default function WelcomePage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { user, token, setAuth } = useAuthStore()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await updateMe({ display_name: name.trim(), locale: i18n.language })
      const { data } = await me()
      if (token) setAuth(data, token)
    } catch {
      // The name is not worth blocking on: they are already signed in, and the
      // placeholder works. Profile can fix it later.
    } finally {
      setBusy(false)
      navigate('/dashboard')
    }
  }

  return (
    <div className="min-h-[100dvh] bg-ivory flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex justify-end mb-3">
          <LanguageSwitcher />
        </div>
        <h1 className="font-display font-bold text-3xl text-navy text-center mb-2">
          {t('welcome.title')}
        </h1>
        <p className="text-center text-muted text-sm font-body mb-8">
          {t('welcome.subtitle')}
        </p>

        <form
          onSubmit={save}
          className="bg-white rounded-card border border-navy/10 p-6 space-y-4"
        >
          <div>
            <label
              htmlFor="welcome-name"
              className="block text-xs font-body font-medium text-navy/60 mb-1"
            >
              {t('welcome.nameLabel')}
            </label>
            <input
              id="welcome-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={user?.display_name ?? ''}
              autoFocus
              maxLength={100}
              data-testid="welcome-name"
              className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            />
            <p className="text-[11px] font-body text-muted mt-1">
              {t('welcome.nameHint')}
            </p>
          </div>
          <button
            type="submit"
            disabled={busy || !name.trim()}
            className="w-full bg-navy text-ivory font-display font-medium py-3 rounded-field text-sm disabled:opacity-50"
          >
            {busy ? '…' : t('welcome.save')}
          </button>
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className="w-full text-xs font-body text-muted"
          >
            {t('welcome.skip')}
          </button>
        </form>
      </div>
    </div>
  )
}
