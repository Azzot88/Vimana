import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createMeetingPlace,
  deleteMeetingPlace,
  listMeetingPlaces,
  makeMeetingPlaceDefault,
  updateMeetingPlace,
  type MeetingPlace,
} from '../api/addresses'
import { listCountries } from '../api/airports'

/** T3.11.07 — the three answers a meeting place is filed under. The country is
 *  required, the city is not: «встречу в аэропорту вылета» is a country-wide
 *  offer, while «у метро Фили» is only findable if you know it is Moscow. */
interface PlaceDraft {
  description: string
  country: string
  city: string
}

const EMPTY_PLACE: PlaceDraft = { description: '', country: '', city: '' }

/**
 * T3.11.07 — the places this person is willing to meet, in their own words.
 *
 * Sits beside `AddressesSection` and behaves the same way — several rows, one
 * default, add / edit / delete — because it is the same kind of list and a
 * second set of manners for it would be a second thing to learn.
 *
 * What it is *not* is an address, which is why it is not a variant of that
 * component. An address is where a parcel is sent and carries the structure the
 * post office needs: country, city, street, postal code. A meeting place is
 * «у метро Фили, у выхода №3» or «Terminal D, departures, by the Costa» — one
 * sentence, and the half that matters is the half no address form has a box
 * for. So the description stays one free-text field and stays the point.
 *
 * T3.11.07 (owner's decision 2026-09-06) — the country and the city sit beside
 * it. Not as structure for the post office, but as the keys the trip form files
 * the place under: it offers meeting places for one end of a route, and a list
 * that has to be read and rejected on every publication is worse than no list.
 *
 * Functions (PROJECT §6.2a):
 * - `MeetingPlacesSection()` — default export.
 *   Called by: `pages/ProfileRulesPage`.
 */
export default function MeetingPlacesSection() {
  const { t, i18n } = useTranslation()
  const [places, setPlaces] = useState<MeetingPlace[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  /* T3.11.07 — a place is filed under a country and a city (owner's decision
     2026-09-06). The description is still the point and still free text; these
     two are the keys the trip form filters on, and without them the form was
     offering a Moscow landmark to somebody arriving in Dubai. */
  const [draft, setDraft] = useState<PlaceDraft>({ ...EMPTY_PLACE })
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editing, setEditing] = useState<PlaceDraft>({ ...EMPTY_PLACE })
  const [countries, setCountries] = useState<Array<{ iso: string; name: string }>>([])

  useEffect(() => {
    let cancelled = false
    listCountries()
      .then(({ data }) => {
        if (cancelled) return
        // Names in the interface language; the list itself is the countries this
        // platform has airports in, which is the same list the address form
        // uses — one vocabulary for "where in the world", not two.
        const display = new Intl.DisplayNames([i18n.language], { type: 'region' })
        setCountries(
          data
            .map((c) => ({ iso: c.iso, name: display.of(c.iso) || c.iso }))
            .sort((a, b) => a.name.localeCompare(b.name, i18n.language)),
        )
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [i18n.language])

  const reload = async () => {
    setLoading(true)
    try {
      const { data } = await listMeetingPlaces()
      setPlaces(data)
      setError('')
    } catch {
      setError(t('profile.meetingPlaces.loadFailed') as string)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const add = async () => {
    if (!draft.description.trim() || !draft.country) return
    try {
      await createMeetingPlace({
        description: draft.description.trim(),
        country_iso: draft.country,
        city: draft.city.trim() || null,
      })
      setDraft({ ...EMPTY_PLACE })
      await reload()
    } catch {
      setError(t('profile.meetingPlaces.saveFailed') as string)
    }
  }

  const saveEdit = async (id: string) => {
    if (!editing.description.trim()) return
    try {
      await updateMeetingPlace(id, {
        description: editing.description.trim(),
        country_iso: editing.country || undefined,
        // Sent as an empty string rather than omitted so a city can be cleared:
        // omission means "leave it alone" on the server, and the two have to
        // stay different.
        city: editing.city.trim(),
      })
      setEditingId(null)
      await reload()
    } catch {
      setError(t('profile.meetingPlaces.saveFailed') as string)
    }
  }

  /** The country and city pair, shared by the add row and the edit row so the
   *  two cannot ask differently. The country is a select over the same list the
   *  address form uses — one vocabulary for "where in the world", not two. */
  const whereFields = (value: PlaceDraft, onChange: (next: PlaceDraft) => void) => (
    <div className="flex flex-wrap gap-2">
      <label className="flex-1 min-w-[9rem]">
        <span className="block text-[11px] font-body text-navy/40 mb-1">
          {t('profile.address.country')}
        </span>
        <select
          value={value.country}
          onChange={(e) => onChange({ ...value, country: e.target.value })}
          className="w-full border border-navy/20 rounded-field px-2 py-2 min-h-[2.75rem] text-sm font-body text-navy bg-white focus:outline-none focus:border-cyan"
        >
          <option value="">—</option>
          {countries.map((c) => (
            <option key={c.iso} value={c.iso}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex-1 min-w-[9rem]">
        <span className="block text-[11px] font-body text-navy/40 mb-1">
          {t('profile.address.city')}{' '}
          <span className="text-navy/30">{t('trips.optional')}</span>
        </span>
        <input
          type="text"
          value={value.city}
          maxLength={150}
          /* Free text, not the address form's geonames typeahead. A meeting
             place is named by the person meeting you, and «Москва» typed by
             hand is the same city as the one in the catalogue — demanding the
             catalogue spelling here would refuse the answer to make the filter
             tidy. */
          onChange={(e) => onChange({ ...value, city: e.target.value })}
          className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
        />
      </label>
    </div>
  )

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
      await reload()
    } catch {
      setError(t('profile.meetingPlaces.saveFailed') as string)
    }
  }

  return (
    <section className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
      <div>
        <h2 className="font-display font-semibold text-sm text-navy">
          {t('profile.meetingPlaces.title')}
        </h2>
        {/* DESIGNGUIDELINES §9b — what this list changes and where it shows up. */}
        <p className="text-[11px] font-body text-navy/50 mt-0.5">
          {t('profile.meetingPlaces.hint')}
        </p>
      </div>

      {loading ? (
        <p className="text-xs font-body text-navy/30">{t('common.loading')}</p>
      ) : places.length === 0 ? (
        <p className="text-xs font-body text-navy/40">
          {t('profile.meetingPlaces.empty')}
        </p>
      ) : (
        <ul className="space-y-2">
          {places.map((place) => (
            <li
              key={place.id}
              className="border border-navy/10 rounded-field p-3 space-y-2"
            >
              {editingId === place.id ? (
                <div className="space-y-2">
                  <input
                    type="text"
                    value={editing.description}
                    maxLength={300}
                    onChange={(e) =>
                      setEditing({ ...editing, description: e.target.value })
                    }
                    className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
                  />
                  {whereFields(editing, setEditing)}
                  <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => saveEdit(place.id)}
                    className="bg-navy text-ivory font-display font-medium px-4 py-2 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid"
                  >
                    {t('common.save')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingId(null)}
                    className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2 min-h-[2.75rem]"
                  >
                    {t('common.cancel')}
                  </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-body text-navy">{place.description}</p>
                      {/* Where it is, under what it says — a place without a
                          country is offered on every route, so saying so is the
                          difference between a filter and a surprise. */}
                      <p className="text-[11px] font-body text-navy/45 mt-0.5">
                        {[place.city, place.country_iso].filter(Boolean).join(', ') ||
                          t('profile.meetingPlaces.anywhere')}
                      </p>
                    </div>
                    {place.is_default && (
                      <span className="shrink-0 text-[10px] font-mono uppercase tracking-wide text-cyan border border-cyan/40 rounded-full px-2 py-0.5">
                        {t('profile.meetingPlaces.default')}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-3 text-xs font-body">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(place.id)
                        setEditing({
                          description: place.description,
                          country: place.country_iso ?? '',
                          city: place.city ?? '',
                        })
                      }}
                      className="text-navy/60 hover:text-navy"
                    >
                      {t('common.edit')}
                    </button>
                    {!place.is_default && (
                      <button
                        type="button"
                        onClick={() => act(() => makeMeetingPlaceDefault(place.id))}
                        className="text-navy/60 hover:text-navy"
                      >
                        {t('profile.meetingPlaces.makeDefault')}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => act(() => deleteMeetingPlace(place.id))}
                      className="text-navy/40 hover:text-danger"
                    >
                      {t('common.delete')}
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="space-y-2 border-t border-navy/10 pt-3">
        <input
          type="text"
          value={draft.description}
          maxLength={300}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          placeholder={t('profile.meetingPlaces.placeholder') as string}
          className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
        />
        {whereFields(draft, setDraft)}
        <button
          type="button"
          onClick={add}
          /* The country is required, so the button says so by staying off
             until it is answered — the alternative is a 422 for a field the
             form never marked. */
          disabled={!draft.description.trim() || !draft.country}
          className="bg-navy text-ivory font-display font-medium px-4 py-2 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {t('profile.meetingPlaces.add')}
        </button>
      </div>

      {error && <p className="text-xs font-mono text-amber">{error}</p>}
    </section>
  )
}
