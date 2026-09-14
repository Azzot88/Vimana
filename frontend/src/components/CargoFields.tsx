import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import type { CargoTemplate } from '../api/cargoTemplates'
import CategorySelect from './CategorySelect'

/** T3.12.03 pt.2 — what a sender says about their cargo, drawn once.
 *
 *  The response to a trip and the template in the cabinet ask the same three
 *  questions, and two copies of the form would drift the day one of them grows
 *  a field. Values are strings because they are what the inputs hold; the page
 *  converts at the moment it sends.
 *
 *  Functions (PROJECT §6.2a):
 *  - `CargoFields` — default export. Called by: `pages/RespondPage`,
 *    `pages/ProfileCargoTemplatesPage`.
 *  - `fieldsFromTemplate(template)` — a template as form values. Called by: the
 *    same two pages.
 */
export interface CargoFieldsValue {
  description: string
  declaredValue: string
  category: string
}

export const EMPTY_CARGO: CargoFieldsValue = {
  description: '',
  declaredValue: '',
  category: '',
}

export function fieldsFromTemplate(template: CargoTemplate): CargoFieldsValue {
  return {
    description: template.description ?? '',
    declaredValue: template.declared_value != null ? String(template.declared_value) : '',
    category: template.category ?? '',
  }
}

interface Props {
  value: CargoFieldsValue
  onChange: (next: CargoFieldsValue) => void
  /** The categories the trip carries; absent in the cabinet, where a template
   *  is not yet about any trip. */
  only?: string[]
  /** The response needs a declared value; a template may leave it for later. */
  valueRequired?: boolean
}

export default function CargoFields({ value, onChange, only, valueRequired }: Props) {
  const { t } = useTranslation()
  const descriptionId = useId()
  const valueId = useId()
  const set = (patch: Partial<CargoFieldsValue>) => onChange({ ...value, ...patch })

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div className="sm:col-span-2">
        <label
          htmlFor={descriptionId}
          className="block text-xs font-body font-medium text-navy/60 mb-1"
        >
          {t('trips.cargoDescription')}
        </label>
        <input
          id={descriptionId}
          type="text"
          value={value.description}
          onChange={(e) => set({ description: e.target.value })}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
        />
      </div>
      <div>
        <label htmlFor={valueId} className="block text-xs font-body font-medium text-navy/60 mb-1">
          {t('trips.declaredValue')}
        </label>
        <input
          id={valueId}
          type="number"
          step="0.01"
          min="0"
          value={value.declaredValue}
          onChange={(e) => set({ declaredValue: e.target.value })}
          required={valueRequired}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan"
          placeholder="100"
        />
      </div>
      <div>
        <span className="block text-xs font-body font-medium text-navy/60 mb-1">
          {t('trips.category')}
        </span>
        {/* T3.11.07 — only what the trip carries, and the whole catalogue when
            it named nothing: a sender picks, never invents. */}
        <CategorySelect
          value={value.category}
          onChange={(category) => set({ category })}
          only={only}
          catalogue
        />
      </div>
    </div>
  )
}
