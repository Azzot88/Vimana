import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { joinDeal } from '../api/participants'
import { useAuthStore } from '../stores/auth'
import MonoText from '../components/MonoText'

/** T3.3 — landing page for a `/join/deal/:token` invite link.
 *
 * Not logged in → redirect to /login with `?next=` back here.
 * Logged in → POST /deals/join/:token, redirect to the deal's chat on OK. */
export default function JoinDealPage() {
  const { t } = useTranslation()
  const { token } = useParams<{ token: string }>()
  const nav = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [state, setState] = useState<'pending' | 'ok' | string>('pending')

  useEffect(() => {
    if (!token) return
    if (!user) {
      nav(`/login?next=/join/deal/${token}`, { replace: true })
      return
    }
    joinDeal(token)
      .then(({ data }) => {
        setState('ok')
        nav(`/deals/${data.deal_id}/vault`, { replace: true })
      })
      .catch((err) => {
        const detail = err?.response?.data?.detail
        setState(typeof detail === 'string' ? detail : t('recipient.joinError'))
      })
  }, [token, user])

  return (
    <div className="max-w-md mx-auto py-16 text-center space-y-4">
      <h1 className="font-display font-bold text-xl text-navy">
        {t('recipient.joinTitle')}
      </h1>
      {state === 'pending' && (
        <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
      )}
      {state !== 'pending' && state !== 'ok' && (
        <p className="text-sm font-body text-red-600">{state}</p>
      )}
    </div>
  )
}
