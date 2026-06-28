import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { createTrip } from '../api/trips'

const CATEGORIES = ['documents', 'electronics', 'clothing', 'food', 'cosmetics', 'other']

export default function NewTripPage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [departAt, setDepartAt] = useState('')
  const [capacity, setCapacity] = useState('')
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (!user?.is_carrier) {
    return (
      <div className="text-center py-24">
        <p className="text-sm font-body text-navy/40">Только перевозчики могут публиковать рейсы</p>
      </div>
    )
  }

  const toggleCategory = (cat: string) => {
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await createTrip({
        origin,
        destination,
        depart_at: departAt,
        capacity: parseFloat(capacity),
        allowed_categories: selectedCategories,
      })
      navigate('/')
    } catch {
      setError('Не удалось создать рейс')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-lg">
      <h1 className="font-display font-bold text-2xl text-navy mb-6">Новый рейс</h1>
      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">Откуда</label>
            <input
              type="text"
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              required
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="Москва"
            />
          </div>
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">Куда</label>
            <input
              type="text"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              required
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              placeholder="Дубай"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">Дата и время вылета</label>
          <input
            type="datetime-local"
            value={departAt}
            onChange={(e) => setDepartAt(e.target.value)}
            required
            className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
          />
        </div>
        <div>
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">Вместимость (кг)</label>
          <input
            type="number"
            step="0.5"
            min="0.5"
            value={capacity}
            onChange={(e) => setCapacity(e.target.value)}
            required
            className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
            placeholder="5"
          />
        </div>
        <div>
          <label className="block text-xs font-body font-medium text-navy/60 mb-2">Разрешённые категории</label>
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => toggleCategory(cat)}
                className={`px-3 py-1 rounded-full text-xs font-mono transition-colors ${
                  selectedCategories.includes(cat)
                    ? 'bg-cyan text-white'
                    : 'bg-ivory text-navy/60 hover:bg-navy/10'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>
        {error && <p className="text-xs font-mono text-orange-600">{error}</p>}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={loading}
            className="bg-navy text-ivory font-display font-medium px-5 py-2.5 rounded-lg text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
          >
            {loading ? 'Сохранение...' : 'Опубликовать рейс'}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="text-sm font-body text-navy/50 hover:text-navy transition-colors px-3"
          >
            Отмена
          </button>
        </div>
      </form>
    </div>
  )
}
