import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { register, login, me } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { APP_VERSION } from '../version'

export default function RegisterPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [isCarrier, setIsCarrier] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!email && !phone) {
      setError('Укажите email или телефон')
      return
    }
    setLoading(true)
    try {
      await register({
        display_name: displayName,
        email: email || undefined,
        phone: phone || undefined,
        password,
        is_carrier: isCarrier,
      })
      const loginVal = email || phone
      const { data: tokenData } = await login({ login: loginVal, password })
      localStorage.setItem('token', tokenData.access_token)
      const { data: user } = await me()
      setAuth(user, tokenData.access_token)
      navigate('/')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        setError('Пользователь с таким email или телефоном уже существует.')
      } else {
        setError('Ошибка сервера. Попробуйте ещё раз.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-ivory flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="font-display font-bold text-4xl text-navy text-center mb-2">
          Vimana
        </h1>
        <p className="text-center text-navy/50 text-sm font-body mb-8">Sacred Logistics</p>
        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              Имя
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="Иван Петров"
            />
          </div>
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="user@example.com"
            />
          </div>
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              Телефон
            </label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="+7 999 000 00 00"
            />
          </div>
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">
              Пароль
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="••••••••"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={isCarrier}
              onChange={(e) => setIsCarrier(e.target.checked)}
              className="w-4 h-4 accent-cyan"
            />
            <span className="text-sm font-body text-navy">Я перевозчик</span>
          </label>
          {error && (
            <p className="text-xs font-mono text-orange-600">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-navy text-ivory font-display font-medium py-2.5 rounded-lg text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
          >
            {loading ? 'Регистрация...' : 'Создать аккаунт'}
          </button>
        </form>
        <div className="flex items-center justify-between mt-4">
          <p className="text-xs font-body text-navy/50">
            Уже есть аккаунт?{' '}
            <Link to="/login" className="text-cyan hover:underline">
              Войти
            </Link>
          </p>
          <span className="font-mono text-xs text-navy/20">v{APP_VERSION}</span>
        </div>
      </div>
    </div>
  )
}
