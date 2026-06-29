import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { me } from '../api/auth'
import { listConnections, type Connection } from '../api/social'
import MonoText from '../components/MonoText'
import { APP_VERSION } from '../version'

export default function ProfilePage() {
  const navigate = useNavigate()
  const { user, token, setAuth, logout } = useAuthStore()
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        if (!user && token) {
          const { data } = await me()
          setAuth(data, token)
        }
        const { data } = await listConnections()
        setConnections(data)
      } catch {
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="max-w-lg space-y-6">
      <h1 className="font-display font-bold text-2xl text-navy">Профиль</h1>

      <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-full bg-navy flex items-center justify-center">
            <span className="text-ivory font-display font-bold text-lg">
              {user?.display_name?.[0]?.toUpperCase() ?? '?'}
            </span>
          </div>
          <div>
            <p className="font-display font-semibold text-lg text-navy">{user?.display_name}</p>
            <p className="text-xs font-mono text-navy/40">
              {user?.is_carrier ? 'Перевозчик' : 'Отправитель'}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 pt-2 border-t border-navy/10">
          {user?.email && (
            <div>
              <p className="text-xs font-body font-medium text-navy/40 mb-0.5">Email</p>
              <MonoText className="text-sm text-navy">{user.email}</MonoText>
            </div>
          )}
          {user?.phone && (
            <div>
              <p className="text-xs font-body font-medium text-navy/40 mb-0.5">Телефон</p>
              <MonoText className="text-sm text-navy">{user.phone}</MonoText>
            </div>
          )}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-navy/10 p-6">
        <p className="text-xs font-body font-medium text-navy/40 mb-1 uppercase tracking-wider">Уровень Бизнес-Активности</p>
        <div className="flex items-baseline gap-2 mt-2">
          <MonoText className="text-3xl font-medium text-navy">—</MonoText>
          <span className="text-xs font-body text-navy/40">Фаза 3</span>
        </div>
        <p className="text-xs font-body text-navy/30 mt-2">Доступно в следующей фазе</p>
      </div>

      <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display font-semibold text-base text-navy">Контакты</h2>
          <Link
            to="/invite"
            className="text-xs font-body text-cyan hover:underline"
          >
            + Пригласить
          </Link>
        </div>
        {loading ? (
          <MonoText className="text-xs text-navy/40">Загрузка...</MonoText>
        ) : connections.length === 0 ? (
          <p className="text-sm font-body text-navy/40">Нет контактов</p>
        ) : (
          <div className="space-y-2">
            {connections.map((conn) => (
              <div key={conn.id} className="flex items-center justify-between py-2 border-b border-navy/5 last:border-0">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-ivory border border-navy/10 flex items-center justify-center">
                    <span className="text-xs font-display font-bold text-navy">
                      {conn.display_name[0]?.toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-body text-navy">{conn.display_name}</p>
                    <p className="text-xs font-mono text-navy/40">{conn.is_carrier ? 'Перевозчик' : 'Отправитель'}</p>
                  </div>
                </div>
                <MonoText className="text-xs text-navy/30">
                  {new Date(conn.connected_at).toLocaleDateString('ru-RU')}
                </MonoText>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={handleLogout}
          className="text-sm font-body text-navy/40 hover:text-navy transition-colors"
        >
          Выйти из аккаунта
        </button>
        <MonoText className="text-xs text-navy/20">v{APP_VERSION}</MonoText>
      </div>
    </div>
  )
}
