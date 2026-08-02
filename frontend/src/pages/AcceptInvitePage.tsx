import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { acceptInvite } from '../api/social'
import MonoText from '../components/MonoText'

/**
 * T_UX.7 pt.3 — every string on this screen used to be Russian, in the source.
 *
 * The product ships six locales; five of them landed here and read Russian. The
 * page is also the first thing a person sees when a friend invites them, which
 * makes it the worst possible place to be untranslated.
 *
 * The outcome is held in `status`, not in the message text: deriving "did it
 * work" from a string is how a translation quietly changes behaviour.
 */
export default function AcceptInvitePage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const authToken = useAuthStore((s) => s.token)
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')

  useEffect(() => {
    if (!authToken) {
      // Read back by `LoginPage` since T_UX.7 pt.2 — before that the invite was
      // dropped on the floor after signing in.
      navigate(`/login?returnUrl=/invite/${token}`, { replace: true })
      return
    }
    if (!token) return
    setStatus('loading')
    acceptInvite(token)
      .then(() => setStatus('success'))
      .catch(() => setStatus('error'))
  }, [token, authToken])

  return (
    <div className="min-h-[100dvh] bg-ivory flex items-center justify-center px-4">
      <div className="w-full max-w-sm text-center space-y-4">
        <h1 className="font-display font-bold text-3xl text-navy">Vimana</h1>
        {status === 'loading' && (
          <MonoText className="text-sm text-navy/40">{t('common.loading')}</MonoText>
        )}
        {status === 'success' && (
          <div
            data-testid="invite-accepted"
            className="bg-white rounded-card border border-success/30 p-6 space-y-3"
          >
            <div className="w-12 h-12 rounded-full bg-success/10 flex items-center justify-center mx-auto">
              <span className="text-success text-xl" aria-hidden="true">✓</span>
            </div>
            <p className="font-display font-semibold text-navy">{t('invite.acceptedTitle')}</p>
            <p className="text-sm font-body text-navy/50">{t('invite.acceptedBody')}</p>
            <button
              type="button"
              onClick={() => navigate('/profile')}
              className="mt-2 bg-navy text-ivory font-display font-medium px-5 py-2.5 rounded-field text-sm hover:bg-navy-mid transition-colors"
            >
              {t('invite.toProfile')}
            </button>
          </div>
        )}
        {status === 'error' && (
          <div className="bg-white rounded-card border border-navy/10 p-6 space-y-3">
            <p className="font-body text-navy/60">{t('invite.acceptFailed')}</p>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="text-sm text-cyan hover:underline font-body"
            >
              {t('notFound.toHome')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
