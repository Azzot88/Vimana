import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { login, me } from '../api/auth'
import { useAuthStore } from '../stores/auth'

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [loginVal, setLoginVal] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data: tokenData } = await login({ login: loginVal, password })
      const { data: user } = await me()
      setAuth(user, tokenData.access_token)
      navigate('/')
    } catch {
      setError('Неверный логин или пароль')
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
              Email или телефон
            </label>
            <input
              type="text"
              value={loginVal}
              onChange={(e) => setLoginVal(e.target.value)}
              required
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="user@example.com"
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
          {error && (
            <p className="text-xs font-mono text-orange-600">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-navy text-ivory font-display font-medium py-2.5 rounded-lg text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
          >
            {loading ? 'Вход...' : 'Войти'}
          </button>
        </form>
        <p className="text-center text-xs font-body text-navy/50 mt-4">
          Нет аккаунта?{' '}
          <Link to="/register" className="text-cyan hover:underline">
            Зарегистрироваться
          </Link>
        </p>
      </div>
    </div>
  )
}
