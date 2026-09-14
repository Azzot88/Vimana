import { useEffect, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createCargoTemplate,
  deleteCargoTemplate,
  listCargoTemplates,
  updateCargoTemplate,
  type CargoTemplate,
} from '../api/cargoTemplates'
import CargoFields, {
  EMPTY_CARGO,
  fieldsFromTemplate,
  type CargoFieldsValue,
} from '../components/CargoFields'
import MonoText from '../components/MonoText'

/** T3.12.03 pt.2 — «Шаблоны груза», a section of the cabinet.
 *
 *  Several templates, each named, kept and edited here (owner, 2026-09-14);
 *  they are also born at the response to a trip, by a checkbox. Editing one
 *  changes the next response it fills and nothing else — a cargo already in a
 *  deal was copied from the form, not linked to the template, and the hint
 *  says so where the edit happens.
 *
 *  Functions (PROJECT §6.2a):
 *  - `ProfileCargoTemplatesPage()` — default export. Called by: `App` at
 *    `/profile/cargo-templates`.
 */
export default function ProfileCargoTemplatesPage() {
  const { t } = useTranslation()
  const nameId = useId()
  const [templates, setTemplates] = useState<CargoTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  /** The template being edited, `'new'` for one being added, or nothing. */
  const [editing, setEditing] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [cargo, setCargo] = useState<CargoFieldsValue>(EMPTY_CARGO)

  const reload = async () => {
    try {
      const { data } = await listCargoTemplates()
      setTemplates(data)
    } catch {
      setError(t('cargoTemplates.loadError'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  const startNew = () => {
    setEditing('new')
    setName('')
    setCargo(EMPTY_CARGO)
    setError('')
  }

  const startEdit = (template: CargoTemplate) => {
    setEditing(template.id)
    setName(template.name)
    setCargo(fieldsFromTemplate(template))
    setError('')
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    const body = {
      name: name.trim(),
      category: cargo.category || null,
      declared_value: cargo.declaredValue === '' ? null : Number(cargo.declaredValue),
      description: cargo.description || null,
    }
    try {
      if (editing === 'new') await createCargoTemplate(body)
      else if (editing) await updateCargoTemplate(editing, body)
      setEditing(null)
      await reload()
    } catch {
      setError(t('cargoTemplates.saveError'))
    }
  }

  const handleDelete = async (template: CargoTemplate) => {
    if (!window.confirm(t('cargoTemplates.deleteConfirm', { name: template.name }))) return
    try {
      await deleteCargoTemplate(template.id)
      if (editing === template.id) setEditing(null)
      await reload()
    } catch {
      setError(t('cargoTemplates.saveError'))
    }
  }

  const form = (
    <form onSubmit={handleSave} className="space-y-3 pt-3 border-t border-navy/10">
      <div className="max-w-sm">
        <label htmlFor={nameId} className="block text-xs font-body font-medium text-navy/60 mb-1">
          {t('cargoTemplates.name')}
        </label>
        <input
          id={nameId}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={60}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
        />
      </div>
      <CargoFields value={cargo} onChange={setCargo} />
      <div className="flex gap-2">
        <button
          type="submit"
          className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-field text-sm hover:bg-navy-mid transition-colors"
        >
          {t('cargoTemplates.save')}
        </button>
        <button
          type="button"
          onClick={() => setEditing(null)}
          className="text-sm font-body text-navy/50 hover:text-navy transition-colors px-3"
        >
          {t('common.cancel')}
        </button>
      </div>
    </form>
  )

  return (
    <section className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display font-semibold text-sm text-navy">
            {t('cargoTemplates.title')}
          </h2>
          <p className="text-[11px] font-body text-navy/50 mt-0.5">{t('cargoTemplates.desc')}</p>
        </div>
        {editing !== 'new' && (
          <button
            type="button"
            onClick={startNew}
            className="border border-navy/20 text-navy font-body px-3 py-1.5 rounded-field text-sm hover:bg-ivory transition-colors"
          >
            {t('cargoTemplates.add')}
          </button>
        )}
      </div>

      {editing === 'new' && form}
      {error && <p className="text-xs font-body text-danger">{error}</p>}

      {loading ? (
        <MonoText className="text-navy/40 text-sm">{t('common.loading')}</MonoText>
      ) : templates.length === 0 ? (
        <p className="text-xs font-body text-navy/40">{t('cargoTemplates.empty')}</p>
      ) : (
        <ul className="divide-y divide-navy/10">
          {templates.map((template) => (
            <li key={template.id} className="py-3 space-y-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-body font-medium text-navy">{template.name}</p>
                  <p className="text-xs font-body text-navy/50 break-words">
                    {[
                      template.category,
                      template.declared_value != null ? String(template.declared_value) : null,
                      template.description,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                </div>
                <div className="flex gap-3 shrink-0">
                  <button
                    type="button"
                    onClick={() => startEdit(template)}
                    className="text-xs font-body text-cyan hover:underline"
                  >
                    {t('cargoTemplates.edit')}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(template)}
                    className="text-xs font-body text-navy/50 hover:text-danger"
                  >
                    {t('cargoTemplates.delete')}
                  </button>
                </div>
              </div>
              {editing === template.id && form}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
