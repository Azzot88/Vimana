import { useEffect, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { updateMe, type PaymentMethod } from '../api/auth'
import { listCountries } from '../api/airports'
import { useAuthStore } from '../stores/auth'

/** T3.11.07 — the ways this carrier can be paid, kept once on the account.
 *
 *  «Наличные при встрече», «перевод на карту Каспи», «Зелле» — the same three
 *  or four answers on every trip, retyped every time, because the trip form
 *  offered a free-text box and a catalogue derived from the corridor. The
 *  catalogue is a good suggestion and a poor memory: it knows what exists in a
 *  country, not what this person actually accepts.
 *
 *  So the answers live here and the trip form picks from them (owner's decision
 *  2026-09-06) — the same shape as the account's currencies.
 *
 *  **Free text, not a closed list.** What people transfer through is local and
 *  changes faster than any vocabulary we could ship, and a carrier naming one
 *  we had not heard of would be told they are wrong. `Trip.payment_systems` is
 *  free text for exactly this reason; this is the carrier's own shortlist of it.
 *
 *  Order is theirs and is kept: the first is what they offer first.
 *
 *  Called by: `pages/ProfileRulesPage`, inside the «Как со мной рассчитаться»
 *  card rather than beside it — one question, one heading.
 */
const MAX_METHODS = 12
const MAX_LENGTH = 60

export default function PaymentMethodsField() {
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const setAuth = useAuthStore((s) => s.setAuth)
  const inputId = useId()

  const methods: PaymentMethod[] = user?.payment_methods ?? []
  const [entry, setEntry] = useState('')
  /* T3.11.07 — the country each method belongs to (owner's decision
     2026-09-06). Empty means «anywhere», which is what «наличные при встрече»
     honestly is; Каспи is KZ and Zelle is US, and the trip form filters on
     exactly this. */
  const [country, setCountry] = useState('')
  const [countries, setCountries] = useState<Array<{ iso: string; name: string }>>([])

  useEffect(() => {
    let cancelled = false
    listCountries()
      .then(({ data }) => {
        if (cancelled) return
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
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  /** Writes the whole list. The store is the only copy — there is no local
   *  mirror to fall out of step with the server, which is what a chip that
   *  survives a failed save would be. */
  const write = async (next: PaymentMethod[]) => {
    setSaving(true)
    setError('')
    try {
      const { data } = await updateMe({ payment_methods: next })
      if (token) setAuth(data, token)
    } catch {
      setError(t('prefs.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const add = () => {
    const value = entry.trim()
    if (!value) return
    // Refused here as well as on the server: a chip that only fails on save is
    // a rule the carrier learns by being rejected.
    if (value.length > MAX_LENGTH || methods.length >= MAX_METHODS) return
    const iso = country || null
    // Deduplicated on the **pair**: «наличные при встрече» in Kazakhstan and the
    // same words in Poland are two entries a carrier may legitimately keep,
    // because the trip form filters on the country.
    if (methods.some((m) => m.name === value && m.country === iso)) {
      setEntry('')
      return
    }
    setEntry('')
    void write([...methods, { name: value, country: iso }])
  }

  return (
    <div className="space-y-2 rounded-field bg-ivory px-3 py-3">
      <div>
        <label
          htmlFor={inputId}
          className="block text-sm font-body font-medium text-navy"
        >
          {t('rules.payment.methodsLabel')}
        </label>
        {/* DESIGNGUIDELINES §9b — every field says what it changes and where it
            shows up. This one is the whole reason it exists: the list is what
            the trip form offers, so a carrier who adds «Каспи» here stops
            typing it on every publication. */}
        <p className="text-xs font-body text-navy/50 mt-0.5">
          {t('rules.payment.methodsDesc')}
        </p>
      </div>

      {methods.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {methods.map((method) => (
            <li
              key={`${method.name}|${method.country ?? ''}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-cyan/30 bg-cyan/10 pl-3 pr-1.5 py-1 text-xs font-body text-navy"
            >
              {method.name}
              {/* The country on the chip, because two chips can read the same
                  and mean different routes. «Везде» is said out loud rather
                  than left blank: a chip with nothing after it would look like
                  a chip that lost its country. */}
              <span className="text-[10px] font-mono text-navy/45">
                {method.country ?? t('rules.payment.methodsAnywhere')}
              </span>
              <button
                type="button"
                disabled={saving}
                onClick={() =>
                  void write(
                    methods.filter(
                      (m) => !(m.name === method.name && m.country === method.country),
                    ),
                  )
                }
                aria-label={`${t('common.delete')} ${method.name}`}
                className="w-5 h-5 rounded-full text-navy/40 hover:text-danger disabled:opacity-40"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        <input
          id={inputId}
          type="text"
          value={entry}
          maxLength={MAX_LENGTH}
          disabled={saving || methods.length >= MAX_METHODS}
          onChange={(e) => setEntry(e.target.value)}
          /* Enter adds, and does not submit the page around it: this control
             sits inside a profile card that has its own save button. */
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          placeholder={t('rules.payment.methodsPlaceholder') as string}
          className="flex-1 border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan disabled:opacity-50"
        />
        <select
          value={country}
          onChange={(e) => setCountry(e.target.value)}
          disabled={saving || methods.length >= MAX_METHODS}
          aria-label={t('profile.address.country') as string}
          className="w-32 border border-navy/20 rounded-field px-2 py-2 min-h-[2.75rem] text-sm font-body text-navy bg-white focus:outline-none focus:border-cyan disabled:opacity-50"
        >
          {/* «Везде» is the default, and it is the honest one: cash at handover
              works on any route, and forcing a country on it would file it
              under one and hide it on the rest. */}
          <option value="">{t('rules.payment.methodsAnywhere')}</option>
          {countries.map((c) => (
            <option key={c.iso} value={c.iso}>
              {c.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={add}
          disabled={saving || !entry.trim() || methods.length >= MAX_METHODS}
          className="px-4 min-h-[2.75rem] rounded-field border border-navy/20 text-xs font-body text-navy/70 hover:border-cyan hover:text-navy disabled:opacity-40"
        >
          {t('common.add')}
        </button>
      </div>

      {methods.length >= MAX_METHODS && (
        <p className="text-[11px] font-body text-navy/45">
          {t('rules.payment.methodsLimit', { max: MAX_METHODS })}
        </p>
      )}
      {error && <p className="text-xs font-mono text-danger">{error}</p>}
    </div>
  )
}
