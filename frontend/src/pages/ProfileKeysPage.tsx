import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { me, type User } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import KeypairSection from '../components/KeypairSection'
import PasskeySection from '../components/PasskeySection'
import SecuritySection from '../components/SecuritySection'

/**
 * T_UX.6 — access and keys, away from the profile.
 *
 * The profile answers "who am I to the other party": name, avatar, activity
 * level, trust, where a parcel goes. This page answers two different questions
 * asked at different moments — how do I get in, and what do I own. Mixing them
 * put a passphrase field next to a delivery address.
 *
 * A route rather than a tab, because things need to link *here*: the "2 codes
 * left" banner, the letter about a spent recovery code, and the reader's
 * "put this key back into the account". A tab lives in component state and
 * cannot be linked to.
 */
export default function ProfileKeysPage() {
  const { t } = useTranslation()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [user, setLocalUser] = useState<User | null>(null)

  /** Re-read after any change here: `SecuritySection` can hand back a fresh
   *  token (a password change retires every other session, including the one
   *  that made it), and the recovery-code counter moves too. */
  const refreshUser = async (newToken?: string) => {
    if (newToken) localStorage.setItem('token', newToken)
    const { data } = await me()
    setLocalUser(data)
    // The store keeps user and token together; after a password change the
    // token in hand is the replacement one, so both are written at once.
    setAuth(data, newToken ?? localStorage.getItem('token') ?? '')
  }

  useEffect(() => {
    void refreshUser()
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-display font-bold text-2xl text-navy">
          {t('profile.keys.title')}
        </h1>
        <Link to="/profile" className="text-sm font-body text-cyan hover:underline">
          ← {t('profile.title')}
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        <div className="space-y-4">
          {user && <SecuritySection user={user} onChanged={refreshUser} />}
          <PasskeySection />
        </div>

        <div className="space-y-4">
          <KeypairSection />

          {/* The reader is a static page outside the app — deliberately, since
              it must work when the app does not. Opening it in a new tab keeps
              that separation visible instead of pretending it is a route. */}
          <div className="bg-white rounded-2xl border border-navy/10 p-5 space-y-3">
            <h2 className="font-display font-semibold text-lg text-navy">
              {t('profile.identity.readerTitle')}
            </h2>
            <p className="text-sm font-body text-navy/60">
              {t('profile.identity.readerHint')}
            </p>
            <a
              href="/reader.html"
              target="_blank"
              rel="noreferrer"
              data-testid="reader-link"
              className="block w-full text-center border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy"
            >
              {t('profile.identity.readerOpen')}
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
