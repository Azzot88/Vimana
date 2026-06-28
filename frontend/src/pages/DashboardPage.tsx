import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { me } from '../api/auth'
import { listDeals, type Deal } from '../api/deals'
import { listTrips, type Trip } from '../api/trips'
import StatusBadge from '../components/StatusBadge'
import MonoText from '../components/MonoText'

export default function DashboardPage() {
  const { user, setAuth, token } = useAuthStore()
  const [deals, setDeals] = useState<Deal[]>([])
  const [trips, setTrips] = useState<Trip[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        if (!user && token) {
          const { data: userData } = await me()
          setAuth(userData, token)
        }
        const [dealsRes, tripsRes] = await Promise.all([listDeals(), listTrips()])
        setDeals(dealsRes.data)
        setTrips(tripsRes.data)
      } catch {
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const currentUser = user
  const myTrips = trips.filter((t) => t.carrier_id === currentUser?.id)
  const asCarrierDeals = deals.filter((d) => d.carrier_id === currentUser?.id)
  const asSenderDeals = deals.filter((d) => d.sender_id === currentUser?.id)
  const activeDeals = deals.filter((d) =>
    ['matched', 'accepted', 'in_transit', 'delivered'].includes(d.status)
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-navy/40 text-sm">Загрузка...</MonoText>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display font-bold text-2xl text-navy">
            {currentUser ? `Добро пожаловать, ${currentUser.display_name}` : 'Dashboard'}
          </h1>
          <p className="text-sm font-body text-navy/50 mt-0.5">
            {currentUser?.is_carrier ? 'Перевозчик' : 'Отправитель'}
          </p>
        </div>
        {currentUser?.is_carrier && (
          <Link
            to="/trips/new"
            className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid transition-colors"
          >
            + Опубликовать рейс
          </Link>
        )}
      </div>

      {activeDeals.length > 0 && (
        <section>
          <h2 className="font-display font-semibold text-lg text-navy mb-3">Активные сделки</h2>
          <div className="grid gap-3">
            {activeDeals.map((deal) => (
              <Link
                key={deal.id}
                to={`/deals/${deal.id}`}
                className="bg-white rounded-xl border border-navy/10 p-4 hover:border-cyan/40 transition-colors flex items-center justify-between"
              >
                <div className="space-y-1">
                  <MonoText className="text-sm text-navy font-medium">
                    {deal.origin} → {deal.destination}
                  </MonoText>
                  <p className="text-xs font-body text-navy/50">
                    {deal.carrier_id === currentUser?.id ? 'Перевозчик' : 'Отправитель'} · {deal.cargo_description}
                  </p>
                </div>
                <StatusBadge status={deal.status} />
              </Link>
            ))}
          </div>
        </section>
      )}

      {currentUser?.is_carrier && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display font-semibold text-lg text-navy">Я везу</h2>
            <Link to="/trips" className="text-xs text-cyan hover:underline font-body">
              Все рейсы →
            </Link>
          </div>
          {myTrips.length === 0 ? (
            <div className="bg-white rounded-xl border border-navy/10 p-6 text-center">
              <p className="text-sm font-body text-navy/40">Нет опубликованных рейсов</p>
              <Link
                to="/trips/new"
                className="inline-block mt-3 text-sm text-cyan hover:underline font-body"
              >
                Опубликовать рейс
              </Link>
            </div>
          ) : (
            <div className="grid gap-3">
              {myTrips.slice(0, 3).map((trip) => (
                <div
                  key={trip.id}
                  className="bg-white rounded-xl border border-navy/10 p-4"
                >
                  <div className="flex items-center justify-between">
                    <MonoText className="text-sm text-navy font-medium">
                      {trip.origin} → {trip.destination}
                    </MonoText>
                    <MonoText className="text-xs text-navy/50">
                      {new Date(trip.depart_at).toLocaleDateString('ru-RU')}
                    </MonoText>
                  </div>
                  <p className="text-xs font-body text-navy/50 mt-1">
                    Вместимость: {trip.capacity} кг
                  </p>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display font-semibold text-lg text-navy">
            {currentUser?.is_carrier ? 'Мои грузы' : 'Мне везут'}
          </h2>
          <Link to="/deals" className="text-xs text-cyan hover:underline font-body">
            Все сделки →
          </Link>
        </div>
        {asCarrierDeals.length === 0 && asSenderDeals.length === 0 ? (
          <div className="bg-white rounded-xl border border-navy/10 p-6 text-center">
            <p className="text-sm font-body text-navy/40">Нет активных сделок</p>
            <Link
              to="/trips"
              className="inline-block mt-3 text-sm text-cyan hover:underline font-body"
            >
              Найти рейс
            </Link>
          </div>
        ) : (
          <div className="grid gap-3">
            {[...asCarrierDeals, ...asSenderDeals].slice(0, 3).map((deal) => (
              <Link
                key={deal.id}
                to={`/deals/${deal.id}`}
                className="bg-white rounded-xl border border-navy/10 p-4 hover:border-cyan/40 transition-colors flex items-center justify-between"
              >
                <div className="space-y-1">
                  <MonoText className="text-sm text-navy font-medium">
                    {deal.origin} → {deal.destination}
                  </MonoText>
                  <p className="text-xs font-body text-navy/50">{deal.cargo_description}</p>
                </div>
                <StatusBadge status={deal.status} />
              </Link>
            ))}
          </div>
        )}
      </section>

      {!currentUser?.is_carrier && (
        <section>
          <h2 className="font-display font-semibold text-lg text-navy mb-3">Я отправляю</h2>
          <div className="bg-white rounded-xl border border-navy/10 p-6 text-center">
            <p className="text-sm font-body text-navy/60 mb-4">
              Найдите перевозчика и отправьте посылку
            </p>
            <Link
              to="/trips"
              className="inline-block bg-amber text-white font-display font-medium px-5 py-2.5 rounded-lg text-sm hover:opacity-90 transition-opacity"
            >
              Найти рейс
            </Link>
          </div>
        </section>
      )}
    </div>
  )
}
