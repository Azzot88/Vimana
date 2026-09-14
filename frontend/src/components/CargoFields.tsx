import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import type { CargoTemplate } from '../api/cargoTemplates'
import CategorySelect from './CategorySelect'

/** T3.12.03 pt.2 / T3.12.04 — what a sender says about their cargo, drawn once.
 *
 *  The response to a trip and the template in the cabinet ask the same
 *  questions, and two copies of the form would drift the day one of them grows
 *  a field. Since T3.12.04 this is the whole cargo: the terms no longer ask for
 *  a weight or «хрупкое», so everything the carrier needs to know about the
 *  parcel is said here, once. Values are strings because they are what the
 *  inputs hold; `cargoFromFields` converts at the moment something is sent.
 *
 *  Functions (PROJECT §6.2a):
 *  - `CargoFields` — default export. Called by: `pages/RespondPage`,
 *    `pages/ProfileCargoTemplatesPage`.
 *  - `fieldsFromTemplate(template)` — a template as form values. Called by: the
 *    same two pages.
 *  - `cargoFromFields(value)` — form values as the API's cargo fields. Called by:
 *    the same two pages.
 */
export interface CargoFieldsValue {
  description: string
  declaredValue: string
  category: string
  weight: string
  /** Length, width, height. */
  dimensions: [string, string, string]
  fragile: boolean
  openOnHandover: boolean
  url: string
}

export const EMPTY_CARGO: CargoFieldsValue = {
  description: '',
  declaredValue: '',
  category: '',
  weight: '',
  dimensions: ['', '', ''],
  fragile: false,
  openOnHandover: false,
  url: '',
}

const str = (v: number | null | undefined) => (v == null ? '' : String(v))

export function fieldsFromTemplate(template: CargoTemplate): CargoFieldsValue {
  const [l, w, h] = template.dimensions_cm ?? []
  return {
    description: template.description ?? '',
    declaredValue: str(template.declared_value),
    category: template.category ?? '',
    weight: str(template.weight_kg),
    dimensions: [str(l), str(w), str(h)],
    fragile: template.fragile,
    openOnHandover: template.open_on_handover,
    url: template.cargo_url ?? '',
  }
}

export interface CargoBody {
  description: string | null
  declared_value: number | null
  category: string | null
  weight_kg: number | null
  dimensions_cm: number[] | null
  fragile: boolean
  open_on_handover: boolean
  cargo_url: string | null
}

export function cargoFromFields(value: CargoFieldsValue): CargoBody {
  const num = (s: string) => (s.trim() === '' ? null : Number(s))
  // Three measurements or none: two sides of a box are not its volume.
  const dims = value.dimensions.map(num)
  return {
    description: value.description.trim() || null,
    declared_value: num(value.declaredValue),
    category: value.category || null,
    weight_kg: num(value.weight),
    dimensions_cm: dims.every((d) => d !== null) ? (dims as number[]) : null,
    fragile: value.fragile,
    open_on_handover: value.openOnHandover,
    cargo_url: value.url.trim() || null,
  }
}

interface Props {
  value: CargoFieldsValue
  onChange: (next: CargoFieldsValue) => void
  /** The categories the trip carries; absent in the cabinet, where a template
   *  is not yet about any trip. */
  only?: string[]
  /** The response needs a weight and a declared value; a template may leave
   *  them for later. */
  required?: boolean
}

const input =
  'w-full border border-navy/20 rounded-field px-3 py-2 text-sm text-navy focus:outline-none focus:border-cyan'
const labelClass = 'block text-xs font-body font-medium text-navy/60 mb-1'

export default function CargoFields({ value, onChange, only, required }: Props) {
  const { t } = useTranslation()
  const descriptionId = useId()
  const valueId = useId()
  const weightId = useId()
  const urlId = useId()
  const set = (patch: Partial<CargoFieldsValue>) => onChange({ ...value, ...patch })
  const setDimension = (i: number, v: string) => {
    const next = [...value.dimensions] as [string, string, string]
    next[i] = v
    set({ dimensions: next })
  }
  const axes = ['length', 'width', 'height'] as const

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div className="sm:col-span-2">
        <label htmlFor={descriptionId} className={labelClass}>
          {t('trips.cargoDescription')}
        </label>
        <input
          id={descriptionId}
          type="text"
          value={value.description}
          onChange={(e) => set({ description: e.target.value })}
          className={`${input} font-body`}
        />
      </div>
      <div>
        <label htmlFor={weightId} className={labelClass}>
          {t('terms.weight')}
        </label>
        <input
          id={weightId}
          type="number"
          step="0.01"
          min="0.01"
          max="100"
          value={value.weight}
          onChange={(e) => set({ weight: e.target.value })}
          required={required}
          className={`${input} font-mono`}
          placeholder="1.5"
        />
      </div>
      <div>
        <label htmlFor={valueId} className={labelClass}>
          {t('trips.declaredValue')}
        </label>
        <input
          id={valueId}
          type="number"
          step="0.01"
          min="0"
          value={value.declaredValue}
          onChange={(e) => set({ declaredValue: e.target.value })}
          required={required}
          className={`${input} font-mono`}
          placeholder="100"
        />
      </div>
      <fieldset className="sm:col-span-2">
        <legend className={labelClass}>{t('cargoFields.dimensions')}</legend>
        <div className="grid grid-cols-3 gap-2">
          {axes.map((axis, i) => (
            <input
              key={axis}
              type="number"
              step="0.1"
              min="0.1"
              aria-label={t(`cargoFields.${axis}`)}
              placeholder={t(`cargoFields.${axis}`)}
              value={value.dimensions[i]}
              onChange={(e) => setDimension(i, e.target.value)}
              className={`${input} font-mono`}
            />
          ))}
        </div>
      </fieldset>
      <div className="sm:col-span-2">
        <span className={labelClass}>{t('trips.category')}</span>
        {/* T3.11.07 — only what the trip carries, and the whole catalogue when
            it named nothing: a sender picks, never invents. */}
        <CategorySelect
          value={value.category}
          onChange={(category) => set({ category })}
          only={only}
          catalogue
        />
      </div>
      <div className="sm:col-span-2">
        <label htmlFor={urlId} className={labelClass}>
          {t('agreement.field.url')}
        </label>
        <input
          id={urlId}
          type="url"
          maxLength={500}
          value={value.url}
          onChange={(e) => set({ url: e.target.value })}
          className={`${input} font-body`}
          placeholder="https://"
        />
      </div>
      <div className="sm:col-span-2 flex flex-wrap gap-4">
        <label className="inline-flex items-center gap-2 text-sm font-body text-navy">
          <input
            type="checkbox"
            checked={value.fragile}
            onChange={(e) => set({ fragile: e.target.checked })}
          />
          {t('agreement.field.fragile')}
        </label>
        {/* T3.12.04 — the sender's consent, given with the cargo and not
            negotiated afterwards (owner, 2026-09-14). */}
        <label className="inline-flex items-center gap-2 text-sm font-body text-navy">
          <input
            type="checkbox"
            checked={value.openOnHandover}
            onChange={(e) => set({ openOnHandover: e.target.checked })}
          />
          {t('agreement.field.openOnHandover')}
        </label>
      </div>
    </div>
  )
}
