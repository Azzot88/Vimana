import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { createTrip } from '../api/trips'
import AirportSelect from '../components/AirportSelect'
import CategorySelect from '../components/CategorySelect'

export default function NewTripPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
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
        <p className="text-sm font-body text-navy/40">{t('trips.carriersOnly')}</p>
      </div>
    )
  }

  const [categoryDraft, setCategoryDraft] = useState('')

  const removeCategory = (cat: string) => {
    setSelectedCategories((prev) => prev.filter((c) => c !== cat))
  }

  const addCategory = (cat: string) => {
    const key = cat.trim().toLowerCase()
    if (!key) return
    setSelectedCategories((prev) => (prev.includes(key) ? prev : [...prev, key]))
    setCategoryDraft('')
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
      setError(t('trips.publishError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-lg">
      <h1 className="font-display font-bold text-2xl text-navy mb-6">{t('trips.newTrip')}</h1>
      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-navy/10 p-4 sm:p-6 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.from')}</label>
            <AirportSelect value={origin} onChange={setOrigin} required placeholder="DXB" />
          </div>
          <div>
            <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.to')}</label>
            <AirportSelect value={destination} onChange={setDestination} required placeholder="JFK" />
          </div>
        </div>
        <div>
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.departureDate')}</label>
          <input
            type="datetime-local"
            value={departAt}
            onChange={(e) => setDepartAt(e.target.value)}
            required
            className="w-full border border-navy/20 rounded-lg px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
          />
        </div>
        <div>
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.capacityKg')}</label>
          <input
            type="number"
            step="0.5"
            min="0.5"
            value={capacity}
            onChange={(e) => setCapacity(e.target.value)}
            required
            className="w-full border border-navy/20 rounded-lg px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
            placeholder="5"
          />
        </div>
        <div>
          <label className="block text-xs font-body font-medium text-navy/60 mb-2">{t('trips.allowedCategories')}</label>
          {selectedCategories.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {selectedCategories.map((cat) => (
                <span
                  key={cat}
                  className="px-3 py-1 rounded-full text-xs font-mono bg-cyan text-white inline-flex items-center gap-1"
                >
                  {t(`categories.${cat}`, { defaultValue: cat })}
                  <button
                    type="button"
                    onClick={() => removeCategory(cat)}
                    className="hover:text-white/80"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          <CategorySelect value={categoryDraft} onChange={addCategory} />
        </div>
        {error && <p className="text-xs font-mono text-orange-600">{error}</p>}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={loading}
            className="flex-1 sm:flex-none bg-navy text-ivory font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
          >
            {loading ? t('common.loading') : t('trips.publish')}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="text-sm font-body text-navy/50 hover:text-navy transition-colors px-3 min-h-[2.75rem]"
          >
            {t('common.cancel')}
          </button>
        </div>
      </form>
    </div>
  )
}
