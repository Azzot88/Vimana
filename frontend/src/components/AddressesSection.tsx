import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createAddress,
  deleteAddress,
  listAddresses,
  makeAddressDefault,
  updateAddress,
  type Address,
  type AddressInput,
} from '../api/addresses'
import api from '../api/client'
import AddressFormFields, { type AddressFormValue } from './AddressFormFields'
import MonoText from './MonoText'

/** T_UX.4 B — replaces the single legacy AddressForm on the profile page.
 *  Shows the user's list of named addresses (Home / Office / …), each with
 *  a default-badge + Edit / Delete / Set-default actions. Add new via a
 *  small inline form. */
export default function AddressesSection() {
  const { t, i18n } = useTranslation()
  const [addresses, setAddresses] = useState<Address[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [countryOptions, setCountryOptions] = useState<Array<{ iso: string; name: string }>>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState<AddressFormValue>(_emptyDraft())

  const reload = async () => {
    setLoading(true)
    try {
      const { data } = await listAddresses()
      setAddresses(data)
    } catch {
      setError('Failed to load addresses')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const { data } = await api.get<Array<{ iso: string; count: number }>>(
          '/api/airports/countries',
        )
        if (cancelled) return
        const display = new Intl.DisplayNames([i18n.language], { type: 'region' })
        setCountryOptions(
          data
            .map((c) => ({ iso: c.iso, name: display.of(c.iso) || c.iso }))
            .sort((a, b) => a.name.localeCompare(b.name)),
        )
      } catch { /* silent */ }
    })()
    return () => {
      cancelled = true
    }
  }, [i18n.language])

  const submitCreate = async () => {
    if (!draft.label.trim() || !draft.country_iso) return
    try {
      await createAddress(_toInput(draft))
      setDraft(_emptyDraft())
      setCreating(false)
      await reload()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Create failed')
    }
  }

  const submitEdit = async () => {
    if (!editingId) return
    try {
      await updateAddress(editingId, _toInput(draft))
      setEditingId(null)
      setDraft(_emptyDraft())
      await reload()
    } catch {
      setError('Update failed')
    }
  }

  const startEdit = (a: Address) => {
    setEditingId(a.id)
    setCreating(false)
    setDraft({
      label: a.label,
      country_iso: a.country_iso,
      city: a.city,
      city_geoname_id: a.city_geoname_id,
      street: a.street,
      postal_code: a.postal_code,
      note: a.note,
    })
  }

  const handleDelete = async (a: Address) => {
    if (!confirm(t('address.confirmDelete', { label: a.label }) as string)) return
    try {
      await deleteAddress(a.id)
      await reload()
    } catch {
      setError('Delete failed')
    }
  }

  const handleMakeDefault = async (a: Address) => {
    try {
      await makeAddressDefault(a.id)
      await reload()
    } catch {
      setError('Set-default failed')
    }
  }

  return (
    <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display font-semibold text-base text-navy">
          {t('address.sectionTitle')}
        </h2>
        {!creating && !editingId && (
          <button
            type="button"
            onClick={() => {
              setCreating(true)
              setEditingId(null)
              setDraft(_emptyDraft())
            }}
            className="text-xs font-body text-cyan hover:underline"
          >
            + {t('address.add')}
          </button>
        )}
      </div>
      {error && <p className="text-xs font-mono text-danger">{error}</p>}
      {loading ? (
        <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
      ) : addresses.length === 0 && !creating ? (
        <p className="text-sm font-body text-navy/40">{t('address.empty')}</p>
      ) : (
        <div className="space-y-2">
          {addresses.map((a) =>
            editingId === a.id ? (
              <div key={a.id} className="border border-cyan rounded-lg p-3 space-y-3">
                <AddressFormFields
                  value={draft}
                  onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
                  countryOptions={countryOptions}
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setEditingId(null)
                      setDraft(_emptyDraft())
                    }}
                    className="text-xs font-body text-navy/50 px-3 py-1.5"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    type="button"
                    onClick={submitEdit}
                    className="bg-navy text-ivory font-display font-medium text-xs px-4 py-1.5 rounded"
                  >
                    {t('common.save')}
                  </button>
                </div>
              </div>
            ) : (
              <div
                key={a.id}
                className="border border-navy/10 rounded-lg p-3 flex items-start justify-between gap-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <p className="font-display font-medium text-sm text-navy truncate">
                      {a.label}
                    </p>
                    {a.is_default && (
                      <span className="text-[10px] font-mono uppercase bg-cyan/15 text-cyan px-1.5 py-0.5 rounded">
                        {t('address.default')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-body text-navy/60">
                    {[a.country_iso, a.city, a.street, a.postal_code]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                  {a.note && (
                    <p className="text-xs font-mono text-navy/40 mt-0.5">{a.note}</p>
                  )}
                </div>
                <div className="flex flex-col gap-1 shrink-0">
                  {!a.is_default && (
                    <button
                      type="button"
                      onClick={() => handleMakeDefault(a)}
                      className="text-[11px] font-body text-cyan hover:underline"
                    >
                      {t('address.makeDefault')}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => startEdit(a)}
                    className="text-[11px] font-body text-navy/60 hover:text-navy"
                  >
                    {t('common.edit')}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(a)}
                    className="text-[11px] font-body text-danger hover:underline"
                  >
                    {t('common.delete')}
                  </button>
                </div>
              </div>
            ),
          )}
        </div>
      )}
      {creating && (
        <div className="border border-cyan rounded-lg p-3 space-y-3">
          <AddressFormFields
            value={draft}
            onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            countryOptions={countryOptions}
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setCreating(false)
                setDraft(_emptyDraft())
              }}
              className="text-xs font-body text-navy/50 px-3 py-1.5"
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              onClick={submitCreate}
              disabled={!draft.label.trim() || !draft.country_iso}
              className="bg-navy text-ivory font-display font-medium text-xs px-4 py-1.5 rounded disabled:opacity-50"
            >
              {t('common.save')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function _emptyDraft(): AddressFormValue {
  return {
    label: '',
    country_iso: '',
    city: null,
    city_geoname_id: null,
    street: null,
    postal_code: null,
    note: null,
  }
}

function _toInput(v: AddressFormValue): AddressInput {
  return {
    label: v.label,
    country_iso: v.country_iso,
    city: v.city,
    city_geoname_id: v.city_geoname_id,
    street: v.street,
    postal_code: v.postal_code,
    note: v.note,
  }
}
