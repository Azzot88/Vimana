import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { acceptInvite } from '../api/social'
import MonoText from '../components/MonoText'

export default function AcceptInvitePage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const authToken = useAuthStore((s) => s.token)
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!authToken) {
      navigate(`/login?returnUrl=/invite/${token}`, { replace: true })
      return
    }
    if (!token) return
    setStatus('loading')
    acceptInvite(token)
      .then(() => {
        setStatus('success')
        setMessage('Связь установлена')
      })
      .catch(() => {
        setStatus('error')
        setMessage('Ссылка недействительна или уже использована')
      })
  }, [token, authToken])

  return (
    <div className="min-h-[100dvh] bg-ivory flex items-center justify-center px-4">
      <div className="w-full max-w-sm text-center space-y-4">
        <h1 className="font-display font-bold text-3xl text-navy">Vimana</h1>
        {status === 'loading' && (
          <MonoText className="text-sm text-navy/40">Подключение...</MonoText>
        )}
        {status === 'success' && (
          <div className="bg-white rounded-card border border-success/30 p-6 space-y-3">
            <div className="w-12 h-12 rounded-full bg-success/10 flex items-center justify-center mx-auto">
              <span className="text-success text-xl">✓</span>
            </div>
            <p className="font-display font-semibold text-navy">{message}</p>
            <p className="text-sm font-body text-navy/50">Контакт добавлен в ваш профиль</p>
            <button
              onClick={() => navigate('/profile')}
              className="mt-2 bg-navy text-ivory font-display font-medium px-5 py-2.5 rounded-field text-sm hover:bg-navy-mid transition-colors"
            >
              Перейти в профиль
            </button>
          </div>
        )}
        {status === 'error' && (
          <div className="bg-white rounded-card border border-navy/10 p-6 space-y-3">
            <p className="font-body text-navy/60">{message}</p>
            <button
              onClick={() => navigate('/')}
              className="text-sm text-cyan hover:underline font-body"
            >
              На главную
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
