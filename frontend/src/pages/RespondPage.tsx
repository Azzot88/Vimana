import { useEffect, useId, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listCargoTemplates, type CargoTemplate } from '../api/cargoTemplates'
import { matchDeal } from '../api/deals'
import { raiseCardWithFiles } from '../api/terms'
import { getTrip, type Trip } from '../api/trips'
import CargoFields, {
  EMPTY_CARGO,
  cargoFromFields,
  fieldsFromTemplate,
  type CargoFieldsValue,
} from '../components/CargoFields'
import DepartureChip from '../components/DepartureChip'
import LeadTimeWarning from '../components/LeadTimeWarning'
import MonoText from '../components/MonoText'
import UBAChip from '../components/UBAChip'
import { usePrefs } from '../hooks/usePrefs'
import { routeChain } from '../lib/format'
import { useAuthStore } from '../stores/auth'

/** T3.12.03 pt.2 — «Отклики»: the screen where a sender answers a trip with
 *  cargo, and a deal begins.
 *
 *  It used to be a form unfolding inside the trip's card on the board. The
 *  owner gave it a page of its own (2026-09-14): the cargo is created here once
 *  and never changes (`D-CARGO-MODEL`), which is too much weight for a panel
 *  that closes when somebody scrolls, and a page has an address a reload and a
 *  link can return to.
 *
 *  **A template fills the form; the form is what is sent.** That is the
 *  snapshot the model asks for: the cargo holds what was on screen at the
 *  press, not a reference to a template the sender may edit tomorrow. A
 *  template's category that this trip does not carry is left unanswered rather
 *  than filled in, so the question looks open instead of failing at the press.
 *
 *  Functions (PROJECT §6.2a):
 *  - `RespondPage()` — default export. Called by: `App` at `/trips/:tripId/respond`.
 */
export default function RespondPage() {
  const { tripId } = useParams<{ tripId: string }>()
  const { t } = useTranslation()
  const prefs = usePrefs()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const templateNameId = useId()

  const [trip, setTrip] = useState<Trip | null>(null)
  const [missing, setMissing] = useState(false)
  const [templates, setTemplates] = useState<CargoTemplate[]>([])
  const [cargo, setCargo] = useState<CargoFieldsValue>(EMPTY_CARGO)
  const [saveTemplate, setSaveTemplate] = useState(false)
  const [templateName, setTemplateName] = useState('')
  /* T3.12.04 — «вот что я отправляю», optional, at the response (owner,
     2026-09-14). Several, because one photograph of a parcel is one side of it. */
  const [photos, setPhotos] = useState<File[]>([])
  /* The deal a failed photo upload left behind: it exists, and saying so with a
     way into it is better than pretending the press did nothing. */
  const [createdDeal, setCreatedDeal] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!tripId) return
    let cancelled = false
    getTrip(tripId)
      .then(({ data }) => {
        if (!cancelled) setTrip(data)
      })
      .catch(() => {
        if (!cancelled) setMissing(true)
      })
    // The templates are a convenience: without them the form is still whole.
    listCargoTemplates()
      .then(({ data }) => {
        if (!cancelled) setTemplates(data)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [tripId])

  const applyTemplate = (template: CargoTemplate) => {
    const fields = fieldsFromTemplate(template)
    const allowed = trip?.allowed_categories ?? []
    if (allowed.length > 0 && !allowed.includes(fields.category)) fields.category = ''
    setCargo(fields)
    setError('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!trip) return
    /* T3.11.27 — the category is not a text input, so `required` cannot carry
       it: named before anything is sent, so the answer says what to do. */
    if (!cargo.category.trim()) {
      setError(t('trips.categoryRequired'))
      return
    }
    setSending(true)
    setError('')
    const body = cargoFromFields(cargo)
    try {
      const { data: deal } = await matchDeal({
        trip_id: trip.id,
        cargo: {
          category: cargo.category,
          declared_value: body.declared_value ?? 0,
          description: body.description ?? undefined,
          weight_kg: body.weight_kg ?? 0,
          dimensions_cm: body.dimensions_cm ?? undefined,
          fragile: body.fragile,
          open_on_handover: body.open_on_handover,
          cargo_url: body.cargo_url ?? undefined,
        },
        save_as_template:
          saveTemplate && templateName.trim() ? templateName.trim() : undefined,
      })
      /* T3.12.04 — the photographs go into the new deal's vault as one card,
         after the deal exists because they hang on it. The server validates
         every file before it writes the card, so a refusal leaves no card
         without its pictures — only a deal without them. */
      if (photos.length > 0) {
        try {
          await raiseCardWithFiles(deal.id, 'cargo.photographed', photos)
        } catch {
          setCreatedDeal(deal.id)
          setError(t('respond.photosFailed'))
          return
        }
      }
      /* T3.11.23 — one press, and you are inside the deal, nested in the chat
         with this carrier. */
      navigate(`/deals/${deal.id}/vault`)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : t('trips.requestError'))
    } finally {
      setSending(false)
    }
  }

  const back = (
    <Link to="/trips" className="text-sm font-body text-navy/50 hover:text-navy">
      ← {t('respond.back')}
    </Link>
  )

  if (missing) {
    return (
      <div className="space-y-4">
        {back}
        <p className="text-sm font-body text-navy/60">{t('respond.tripGone')}</p>
      </div>
    )
  }
  if (!trip) {
    return (
      <div className="text-center py-12">
        <MonoText className="text-navy/40 text-sm">{t('common.loading')}</MonoText>
      </div>
    )
  }

  // The same two conditions under which the board hides the button.
  const refusal =
    trip.carrier_id === user?.id
      ? t('respond.ownTrip')
      : user?.active_mode === 'carrier'
        ? t('respond.notForCarrier')
        : null

  return (
    <div className="space-y-6 max-w-3xl">
      {back}
      <h1 className="font-display font-bold text-2xl text-navy">{t('respond.title')}</h1>

      <section
        data-testid="respond-trip"
        className="bg-white rounded-card border border-navy/10 p-4 sm:p-5 space-y-2"
      >
        <MonoText className="text-base text-navy font-medium">{routeChain(trip)}</MonoText>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-body text-navy/50">
          <span className="inline-flex items-center gap-1.5">
            {t('trips.carrier')}:{' '}
            <Link
              to={`/carriers/${trip.carrier_id}`}
              className="text-navy font-medium hover:text-cyan transition-colors underline decoration-navy/20 underline-offset-2"
            >
              {trip.carrier_name}
            </Link>
            <UBAChip uba={trip.carrier_uba} level={trip.carrier_uba_level} />
          </span>
          <MonoText className="text-xs">{prefs.dateTime(trip.depart_at)}</MonoText>
          <DepartureChip trip={trip} />
        </div>
      </section>

      {refusal ? (
        <p className="text-sm font-body text-navy/60">{refusal}</p>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-card border border-navy/10 p-4 sm:p-5 space-y-4"
        >
          <div className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-xs font-display font-semibold text-navy/60 uppercase tracking-wide">
                {t('respond.template')}
              </p>
              <Link
                to="/profile/cargo-templates"
                className="text-xs font-body text-cyan hover:underline"
              >
                {t('respond.manageTemplates')}
              </Link>
            </div>
            {templates.length === 0 ? (
              <p className="text-xs font-body text-navy/40">{t('respond.noTemplates')}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {templates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => applyTemplate(template)}
                    className="border border-navy/20 text-navy font-body px-3 py-1.5 rounded-field text-sm hover:bg-ivory transition-colors"
                  >
                    {template.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          <CargoFields
            value={cargo}
            onChange={setCargo}
            only={trip.allowed_categories}
            required
          />

          <div>
            <label className="block">
              <span className="block text-xs font-body font-medium text-navy/60 mb-1">
                {t('terms.attachPhotos')}
              </span>
              <input
                type="file"
                multiple
                /* Every picture: what is acceptable is decided by the bytes,
                   server-side, not by a list of types here. */
                accept="image/*"
                onChange={(e) => setPhotos(Array.from(e.target.files ?? []))}
                className="text-xs font-body"
              />
            </label>
            {photos.length > 0 && (
              <p className="mt-1 text-[11px] font-body text-navy/40">
                {t('terms.photosChosen', { count: photos.length })}
              </p>
            )}
          </div>

          {/* T3.11.06 — «не успеваете», at the moment a sender is deciding. */}
          <LeadTimeWarning
            origin={trip.origin}
            destination={trip.destination}
            category={cargo.category}
            departAt={trip.depart_at}
          />

          <div className="space-y-2">
            <label className="inline-flex items-center gap-2 text-sm font-body text-navy">
              <input
                type="checkbox"
                checked={saveTemplate}
                onChange={(e) => setSaveTemplate(e.target.checked)}
              />
              {t('respond.saveAsTemplate')}
            </label>
            {saveTemplate && (
              <div className="max-w-sm">
                <label
                  htmlFor={templateNameId}
                  className="block text-xs font-body font-medium text-navy/60 mb-1"
                >
                  {t('respond.templateName')}
                </label>
                <input
                  id={templateNameId}
                  type="text"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  required
                  maxLength={60}
                  className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
                />
              </div>
            )}
          </div>

          {error && <p className="text-xs font-mono text-amber">{error}</p>}
          {createdDeal && (
            <Link
              to={`/deals/${createdDeal}/vault`}
              className="inline-block text-sm font-body text-cyan hover:underline"
            >
              {t('respond.openDeal')}
            </Link>
          )}

          <button
            type="submit"
            disabled={sending || createdDeal !== null}
            className="bg-amber text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {sending ? t('trips.submitting') : t('trips.submit')}
          </button>
        </form>
      )}
    </div>
  )
}
