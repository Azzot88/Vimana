import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listCategories, type Category } from '../api/categories'

/** Available categories, picked by clicking.
 *
 *  The typeahead this replaces asked people to name a category before it would
 *  show them one, which works only if you already know what the set contains.
 *  A carrier deciding what they are willing to take is browsing, not searching:
 *  the whole set is on screen, and a click marks a chip chosen.
 *
 *  T3.11.07 — one set of chips, not two lists.
 *
 *  Until now a chosen category moved from "available" to "chosen", which meant
 *  every click rearranged the row under the cursor and the next click landed on
 *  something the carrier had not aimed at. Chips stay where they are and gain a
 *  tick. It also halves the vertical space, which matters once this lives in a
 *  step of a wizard rather than a full page.
 *
 *  The first `VISIBLE` are shown and the rest hide behind "more". Order comes
 *  from the server (`usage_count`, then the market frequency seeded in 0063) —
 *  deliberately not re-sorted here: a picker that orders by its own rule would
 *  disagree with the one the API decided, and the disagreement would be
 *  invisible.
 */
interface Props {
  selected: string[]
  onChange: (next: string[]) => void
}

/** Enough to cover the market's real answers — documents, parcels, clothing,
 *  medicine, electronics account for 86.2 / ≈71 / 34 / 32.8 / 15 % of posts —
 *  without turning the step into a list to work through. */
const VISIBLE = 6

export default function CategoryBubbles({ selected, onChange }: Props) {
  const { t } = useTranslation()
  const [all, setAll] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    listCategories('')
      .then(({ data }) => setAll(data))
      .catch(() => setAll([]))
      .finally(() => setLoading(false))
  }, [])

  const label = (key: string) => t(`categories.${key}`, { defaultValue: key })

  const toggle = (key: string) =>
    onChange(
      selected.includes(key)
        ? selected.filter((c) => c !== key)
        : [...selected, key],
    )

  // A chosen category is never hidden behind "more": collapsing the list must
  // not take an answer off the screen.
  const hidden = all.slice(VISIBLE).filter((c) => !selected.includes(c.name_key))
  const shown = expanded ? all : all.filter((c) => !hidden.includes(c))

  if (loading) {
    return <p className="text-xs font-body text-navy/30">{t('common.loading')}</p>
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {shown.map((c) => {
          const chosen = selected.includes(c.name_key)
          return (
            <button
              key={c.name_key}
              type="button"
              aria-pressed={chosen}
              onClick={() => toggle(c.name_key)}
              className={`px-3 py-2 min-h-[2.75rem] rounded-field text-xs font-body border inline-flex items-center gap-1.5 transition-colors ${
                chosen
                  ? 'border-cyan bg-cyan/10 text-navy'
                  : 'border-navy/20 text-navy/60 hover:border-navy/40'
              }`}
            >
              {label(c.name_key)}
              {chosen && <span aria-hidden>✓</span>}
            </button>
          )
        })}

        {!expanded && hidden.length > 0 && (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="px-3 py-2 min-h-[2.75rem] rounded-field text-xs font-body border border-dashed border-navy/25 text-navy/50 hover:border-cyan hover:text-navy transition-colors"
          >
            {t('trips.categoriesMore', { count: hidden.length })}
          </button>
        )}
      </div>

      {selected.length === 0 && (
        <p className="text-[11px] font-body text-navy/30">
          {t('trips.categoriesNoneChosen')}
        </p>
      )}
    </div>
  )
}
