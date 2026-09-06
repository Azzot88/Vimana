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
 * for. So there is one field here, and it is free text.
 *
 * Functions (PROJECT §6.2a):
 * - `MeetingPlacesSection()` — default export.
 *   Called by: `pages/ProfileRulesPage`.
 */
export default function MeetingPlacesSection() {
  const { t } = useTranslation()
  const [places, setPlaces] = useState<MeetingPlace[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingText, setEditingText] = useState('')

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
    const text = draft.trim()
    if (!text) return
    try {
      await createMeetingPlace(text)
      setDraft('')
      await reload()
    } catch {
      setError(t('profile.meetingPlaces.saveFailed') as string)
    }
  }

  const saveEdit = async (id: string) => {
    const text = editingText.trim()
    if (!text) return
    try {
      await updateMeetingPlace(id, text)
      setEditingId(null)
      await reload()
    } catch {
      setError(t('profile.meetingPlaces.saveFailed') as string)
    }
  }

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
                <div className="flex flex-wrap gap-2">
                  <input
                    type="text"
                    value={editingText}
                    maxLength={300}
                    onChange={(e) => setEditingText(e.target.value)}
                    className="flex-1 min-w-[12rem] border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
                  />
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
              ) : (
                <>
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-body text-navy">{place.description}</p>
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
                        setEditingText(place.description)
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

      <div className="flex flex-wrap gap-2 border-t border-navy/10 pt-3">
        <input
          type="text"
          value={draft}
          maxLength={300}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t('profile.meetingPlaces.placeholder') as string}
          className="flex-1 min-w-[12rem] border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
        />
        <button
          type="button"
          onClick={add}
          disabled={!draft.trim()}
          className="bg-navy text-ivory font-display font-medium px-4 py-2 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {t('profile.meetingPlaces.add')}
        </button>
      </div>

      {error && <p className="text-xs font-mono text-amber">{error}</p>}
    </section>
  )
}
