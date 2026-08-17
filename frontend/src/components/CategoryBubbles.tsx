import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listCategories, type Category } from '../api/categories'

/** Available categories, picked by clicking.
 *
 *  The typeahead this replaces asked people to name a category before it would
 *  show them one, which works only if you already know what the set contains.
 *  A carrier deciding what they are willing to take is browsing, not searching:
 *  the whole set is on screen, and a click moves a bubble from "available" to
 *  "chosen".
 */
interface Props {
  selected: string[]
  onChange: (next: string[]) => void
}

export default function CategoryBubbles({ selected, onChange }: Props) {
  const { t } = useTranslation()
  const [all, setAll] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listCategories('')
      .then(({ data }) => setAll(data))
      .catch(() => setAll([]))
      .finally(() => setLoading(false))
  }, [])

  const label = (key: string) => t(`categories.${key}`, { defaultValue: key })
  const available = all.filter((c) => !selected.includes(c.name_key))

  const add = (key: string) => onChange([...selected, key])
  const remove = (key: string) => onChange(selected.filter((c) => c !== key))

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[11px] font-body text-navy/40 mb-1.5">
          {t('trips.categoriesChosen')}
        </p>
        {selected.length === 0 ? (
          <p className="text-xs font-body text-navy/30">
            {t('trips.categoriesNoneChosen')}
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {selected.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => remove(key)}
                className="px-3 py-1 rounded-full text-xs font-mono bg-cyan text-white inline-flex items-center gap-1 hover:opacity-90"
                aria-label={`${label(key)} — ${t('trips.categoriesRemove')}`}
              >
                {label(key)}
                <span aria-hidden>×</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <p className="text-[11px] font-body text-navy/40 mb-1.5">
          {t('trips.categoriesAvailable')}
        </p>
        {loading ? (
          <p className="text-xs font-body text-navy/30">{t('common.loading')}</p>
        ) : available.length === 0 ? (
          <p className="text-xs font-body text-navy/30">
            {t('trips.categoriesAllChosen')}
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {available.map((c) => (
              <button
                key={c.name_key}
                type="button"
                onClick={() => add(c.name_key)}
                className="px-3 py-1 rounded-full text-xs font-mono border border-navy/20 text-navy/70 hover:border-cyan hover:text-cyan"
              >
                {label(c.name_key)}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
