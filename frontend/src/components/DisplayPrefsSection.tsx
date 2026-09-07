import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CURRENCIES, MAX_ACCOUNT_CURRENCIES, updateMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { formatDateTime, formatWeight, type DateStyle, type WeightUnit } from '../lib/format'
import MonoText from './MonoText'

/** T_UX.14 — units and date style, and since T_UX.21 nothing else.
 *
 *  The carriage rules used to sit here too, which put the carrier's standing
 *  terms — a thing they send to clients — in the same box as the clock format.
 *  They moved to «Мои правила» with the rest of the operational text.
 *
 *  The preview under the switches is not decoration. "European" and "American"
 *  mean nothing until you see `17.08.2026, 14:30` next to `08/17/2026, 02:30 PM`
 *  — the label describes a convention, the sample describes what will actually
 *  be on the screen.
 */
export default function DisplayPrefsSection() {
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const setAuth = useAuthStore((s) => s.setAuth)

  const [unit, setUnit] = useState<WeightUnit>((user?.unit_weight as WeightUnit) ?? 'kg')
  const [style, setStyle] = useState<DateStyle>((user?.date_format as DateStyle) ?? 'eu')
  // T3.11.07 — a list, and an ordered one: the first entry is what the trip
  // form pre-fills. Held locally so a click paints immediately; the server's
  // answer replaces it, and a failure puts the old list back (`saveCurrencies`).
  const [currencies, setCurrencies] = useState<string[]>(
    user?.default_currencies?.length ? user.default_currencies : ['USD'],
  )
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const save = async (patch: Record<string, unknown>) => {
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const { data } = await updateMe(patch)
      if (token) setAuth(data, token)
      setSaved(true)
    } catch {
      setError(t('prefs.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  /** T3.11.07 — write the list, and put the old one back if the write failed.
   *
   *  The two switches above can afford to leave the optimistic value on screen:
   *  either state is a legal answer, and the next render corrects it. A currency
   *  list cannot — a chip left lit after a refused PATCH tells the carrier they
   *  price in something the server has never heard of. */
  const saveCurrencies = async (next: string[]) => {
    const previous = currencies
    setCurrencies(next)
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const { data } = await updateMe({ default_currencies: next })
      if (token) setAuth(data, token)
      setCurrencies(data.default_currencies?.length ? data.default_currencies : next)
      setSaved(true)
    } catch {
      setCurrencies(previous)
      setError(t('prefs.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  /** Add or remove one code. The last one cannot be removed and the limit is
   *  enforced here as well as on the server: a chip that only fails on save is
   *  a rule the person learns by being refused. */
  const toggleCurrency = (code: string) => {
    if (currencies.includes(code)) {
      if (currencies.length === 1) return
      void saveCurrencies(currencies.filter((c) => c !== code))
      return
    }
    if (currencies.length >= MAX_ACCOUNT_CURRENCIES) return
    void saveCurrencies([...currencies, code])
  }

  const pick = <T extends string>(
    current: T,
    value: T,
    label: string,
    onPick: (v: T) => void,
  ) => (
    <button
      type="button"
      onClick={() => onPick(value)}
      /* T_UX.21 — these switches were the only writers left once the rules
         textarea moved out, and they save on click. Locking them for the
         round-trip stops a double tap from racing two PATCHes whose order
         decides the stored value. */
      disabled={saving}
      className={`px-3 py-1.5 rounded-full text-xs font-body border disabled:opacity-60 ${
        current === value
          ? 'border-cyan text-cyan bg-cyan/5'
          : 'border-navy/15 text-navy/60'
      }`}
    >
      {label}
    </button>
  )

  const sample = new Date().toISOString()

  return (
    <section className="bg-white rounded-card border border-navy/10 p-6 space-y-5">
      <div>
        <h2 className="font-display font-semibold text-base text-navy">{t('prefs.title')}</h2>
        <p className="text-xs font-body text-navy/50 mt-0.5">{t('prefs.hint')}</p>
      </div>

      <div className="space-y-2">
        <div>
          <p className="text-sm font-body font-medium text-navy">{t('prefs.weight')}</p>
          {/* T_UX.22 — the line that was missing: a setting nobody can see the
              effect of is one nobody touches. Says where the choice shows up,
              not just what it is called. */}
          <p className="text-xs font-body text-navy/50 mt-0.5">{t('prefs.weightDesc')}</p>
        </div>
        <div className="flex gap-2">
          {pick(unit, 'kg' as WeightUnit, t('prefs.kg'), (v) => {
            setUnit(v)
            void save({ unit_weight: v })
          })}
          {pick(unit, 'lb' as WeightUnit, t('prefs.lb'), (v) => {
            setUnit(v)
            void save({ unit_weight: v })
          })}
        </div>
        {/* The example is the whole argument for the switch, so it is shown at
            reading size on its own surface rather than as an 11px grey tail.
            "European" and "American" mean nothing until the sample is legible. */}
        <div className="rounded-field bg-ivory px-3 py-2">
          <p className="text-[11px] font-body text-navy/50">{t('prefs.example')}</p>
          <MonoText className="text-base text-navy">{formatWeight(5, unit)}</MonoText>
        </div>
      </div>

      <div className="space-y-2 pt-1 border-t border-navy/5">
        <div className="pt-3">
          <p className="text-sm font-body font-medium text-navy">{t('prefs.dates')}</p>
          <p className="text-xs font-body text-navy/50 mt-0.5">{t('prefs.datesDesc')}</p>
        </div>
        <div className="flex gap-2">
          {pick(style, 'eu' as DateStyle, t('prefs.european'), (v) => {
            setStyle(v)
            void save({ date_format: v })
          })}
          {pick(style, 'us' as DateStyle, t('prefs.american'), (v) => {
            setStyle(v)
            void save({ date_format: v })
          })}
        </div>
        <div className="rounded-field bg-ivory px-3 py-2">
          <p className="text-[11px] font-body text-navy/50">{t('prefs.example')}</p>
          <MonoText className="text-base text-navy">
            {formatDateTime(sample, style, i18n.language)}
          </MonoText>
        </div>
      </div>

      {/* T3.11.07 — the currencies new trips may start in.
          Unlike the two above this one is **not** display-only: it decides what
          a published trip is priced in, which is why it sits under its own
          heading and why the note about storage below no longer speaks for it.
          A closed list rather than free text: a typo in a currency code is a
          price nobody can compare.

          Several rather than one (owner's decision 2026-09-06). A carrier
          working two corridors quotes in two currencies, and one who settles in
          a stablecoin quotes in that as well; asking them to pick one and retype
          the rest on every trip is asking the wrong question. */}
      <div className="space-y-3 pt-1 border-t border-navy/5">
        <div className="pt-3">
          <p className="text-sm font-body font-medium text-navy">
            {t('prefs.currency')}
          </p>
          <p className="text-xs font-body text-navy/50 mt-0.5">
            {t('prefs.currencyDesc')}
          </p>
        </div>

        {/* The chosen ones in the order they are stored. This strip exists
            because the order carries a meaning the alphabetical grid cannot
            show: the first entry is the one a new trip opens in. Promoting is a
            click on the chip itself; removing is the × beside it, so neither
            action can be taken by mistake for the other. */}
        <div className="rounded-field bg-ivory px-3 py-2 space-y-1.5">
          <p className="text-[11px] font-body text-navy/50">
            {t('prefs.currencyChosen')}
          </p>
          <ol className="flex flex-wrap items-center gap-2">
            {currencies.map((code, i) => (
              <li key={code} className="flex items-center">
                <button
                  type="button"
                  onClick={() => saveCurrencies([code, ...currencies.filter((c) => c !== code)])}
                  disabled={saving || i === 0}
                  title={i === 0 ? undefined : t('prefs.currencyMakePrimary')}
                  className={`flex items-center gap-1.5 rounded-l-full rounded-r-none border border-r-0 px-3 py-1.5 text-xs font-body disabled:cursor-default ${
                    i === 0
                      ? 'border-cyan bg-cyan/10 text-navy'
                      : 'border-navy/15 text-navy/70 hover:border-cyan'
                  }`}
                >
                  <MonoText className="text-xs text-navy">{code}</MonoText>
                  {i === 0 && (
                    <span className="text-[10px] text-cyan">
                      {t('prefs.currencyPrimary')}
                    </span>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => toggleCurrency(code)}
                  disabled={saving || currencies.length === 1}
                  aria-label={`${t('prefs.currencyRemove')} ${code}`}
                  title={
                    currencies.length === 1
                      ? t('prefs.currencyLast')
                      : t('prefs.currencyRemove')
                  }
                  className={`rounded-r-full border px-2 py-1.5 text-xs font-body text-navy/40 hover:text-danger disabled:opacity-40 disabled:hover:text-navy/40 ${
                    i === 0 ? 'border-cyan bg-cyan/10' : 'border-navy/15'
                  }`}
                >
                  ×
                </button>
              </li>
            ))}
          </ol>
        </div>

        <div className="space-y-1.5">
          <p className="text-[11px] font-body text-navy/50">
            {t('prefs.currencyAll')}
          </p>
          {/* Alphabetical, crypto and stablecoins in the same run rather than in
              a section of their own: to somebody who prices in USDT it is a
              currency, not a category.

              Every chip carries a bubble naming the currency and saying in a
              breath what it is — `ZEC` and `RSD` are codes almost nobody reads
              cold. It is `aria-describedby`, not a `title`: the description is
              in the accessibility tree at all times, and appears on
              `focus-within` as well as on hover, so it is reachable from the
              keyboard rather than mouse-only. */}
          <div className="flex flex-wrap gap-2">
            {CURRENCIES.map((code) => {
              const chosen = currencies.includes(code)
              const full = !chosen && currencies.length >= MAX_ACCOUNT_CURRENCIES
              const last = chosen && currencies.length === 1
              return (
                <span key={code} className="relative group inline-flex">
                  <button
                    type="button"
                    onClick={() => toggleCurrency(code)}
                    aria-pressed={chosen}
                    aria-describedby={`currency-info-${code}`}
                    disabled={saving || full || last}
                    className={`px-3 py-1.5 rounded-full text-xs font-mono border disabled:opacity-40 ${
                      chosen
                        ? 'border-cyan text-cyan bg-cyan/5'
                        : 'border-navy/15 text-navy/60'
                    }`}
                  >
                    {code}
                  </button>
                  <span
                    role="tooltip"
                    id={`currency-info-${code}`}
                    className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-44 -translate-x-1/2 rounded-field bg-navy px-3 py-2 text-[11px] font-body leading-snug text-white opacity-0 shadow-lift transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
                  >
                    <span className="block font-medium">
                      {t(`prefs.currencyName.${code}`)}
                    </span>
                    <span className="block text-white/70">
                      {t(`prefs.currencyInfo.${code}`)}
                    </span>
                  </span>
                </span>
              )
            })}
          </div>
          {currencies.length >= MAX_ACCOUNT_CURRENCIES && (
            <p className="text-[11px] font-body text-navy/45">
              {t('prefs.currencyLimit', { max: MAX_ACCOUNT_CURRENCIES })}
            </p>
          )}
        </div>
      </div>

      {/* Said once at the bottom rather than twice above: the weight and date
          switches are display-only, and neither changes a stored value. */}
      <p className="text-xs font-body text-navy/45 border-t border-navy/5 pt-3">
        {t('prefs.storageNote')}
      </p>

      {error && <p className="text-xs font-body text-danger">{error}</p>}
      {saved && !error && (
        <p className="text-xs font-body text-success">{t('prefs.saved')}</p>
      )}
    </section>
  )
}
