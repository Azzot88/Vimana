import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import AddressesSection from '../components/AddressesSection'
import PaymentMethodsField from '../components/PaymentMethodsField'
import MeetingPlacesSection from '../components/MeetingPlacesSection'
import StandingNoteSection from '../components/StandingNoteSection'
import { updateMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'

/** T3.11.27 — the choices offered for the cancellation timeout.
 *
 *  A dropdown rather than a free number: the answer is «сколько я готов ждать»,
 *  and the difference between 47 and 48 hours is not a decision anybody is
 *  making. The server accepts 1–168, so a typed value stays legal — this is
 *  about not asking for one.
 */
const CANCEL_TIMEOUTS = [6, 12, 24, 48, 72, 168]

/**
 * T_UX.21 — «Мои правила»: what a carrier writes once and sends in chat.
 *
 * Operational and reusable, which is the line that decides what belongs here.
 * Trips and missions do not: they are the work itself and live on the panel.
 * These are the settings the work is done with.
 *
 * Second in the nav, above the trust circles, because it is the section a
 * working carrier opens repeatedly and the others are read once.
 *
 * **Payment is text and only text for now.** The method catalogue (HodlHodl's
 * model: a table of methods plus the carrier's selection) was deferred by the
 * owner — the platform moves no money yet, cards are Фаза 4 and escrow Фаза 5.
 * So the copy says how to settle with this person and never implies the
 * platform is party to it (DESIGNGUIDELINES §9.1).
 */
export default function ProfileRulesPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // T_UX.16 — somebody sent here from a chat to add a missing address gets a
  // way back to that exact conversation. The banner moved with the addresses:
  // it is the address form it belongs to, not the profile page it used to
  // share with it.
  const returnTo = searchParams.get('return_to')

  // T3.11.27 — owner's rule 2026-09-07: «Таймаут односторонней отмены
  // отправитель настраивает у себя в личном кабинете. Это глобальная настройка
  // для всех сделок». It lives here rather than in «Регион и форматы» because
  // it is not a display preference: it decides when somebody else's deal
  // closes.
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const setAuth = useAuthStore((s) => s.setAuth)
  const [hours, setHours] = useState<number>(user?.cancel_timeout_hours ?? 48)
  const [timeoutError, setTimeoutError] = useState('')

  const saveTimeout = async (next: number) => {
    const previous = hours
    setHours(next)
    setTimeoutError('')
    try {
      const { data } = await updateMe({ cancel_timeout_hours: next })
      if (token) setAuth(data, token)
    } catch {
      // Put the old value back rather than leave the new one lit: a select
      // showing 6 hours after a refused PATCH tells somebody their deals close
      // eight times sooner than they do.
      setHours(previous)
      setTimeoutError(t('prefs.saveFailed'))
    }
  }

  return (
    <div className="space-y-4">
      {returnTo && (
        <div className="rounded-card border border-cyan/40 bg-cyan/5 px-4 py-3 flex flex-wrap items-center gap-3">
          <p className="text-sm font-body text-navy/70">{t('address.returnHint')}</p>
          <button
            type="button"
            onClick={() => navigate(returnTo)}
            className="px-4 py-2 rounded-field bg-cyan text-white text-sm font-body"
          >
            {t('address.backToChat')}
          </button>
        </div>
      )}

      {/* T_UX.22 — one card, two fields. To the reader the carriage rules and
          "how I work" are the same answer to the same question, and they were
          two cards with two Save buttons stacked on top of each other. They
          stay two columns underneath, because they behave differently: the
          carriage rules are copied into each trip (T_UX.15), the working notes
          are not. */}
      <StandingNoteSection
        titleKey="rules.work.title"
        descKey="rules.work.desc"
        fields={[
          {
            name: 'carriage_rules',
            labelKey: 'rules.work.carriageLabel',
            descKey: 'rules.work.carriageDesc',
          },
          {
            name: 'interaction_rules',
            labelKey: 'rules.work.interactionLabel',
            descKey: 'rules.work.interactionDesc',
            placeholderKey: 'rules.work.interactionPlaceholder',
          },
        ]}
      />
      <section className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
        <div>
          <h2 className="font-display font-semibold text-sm text-navy">
            {t('rules.cancelTimeout.title')}
          </h2>
          {/* DESIGNGUIDELINES §9b — say what it changes and where it shows up.
              The departure cap is part of the rule, not a footnote: on a flight
              tomorrow a 72-hour patience is a 20-hour one. */}
          <p className="text-[11px] font-body text-navy/50 mt-0.5">
            {t('rules.cancelTimeout.hint')}
          </p>
        </div>
        <label className="block max-w-xs">
          <span className="block text-xs font-body text-navy/40 mb-1">
            {t('rules.cancelTimeout.label')}
          </span>
          <select
            value={hours}
            onChange={(e) => void saveTimeout(Number(e.target.value))}
            className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm"
          >
            {CANCEL_TIMEOUTS.map((h) => (
              <option key={h} value={h}>
                {t('rules.cancelTimeout.hours', { count: h })}
              </option>
            ))}
          </select>
        </label>
        {timeoutError && (
          <p className="text-xs font-body text-danger">{timeoutError}</p>
        )}
      </section>
      <AddressesSection />
      {/* T3.11.07 — beside the addresses, because the trip form offers both and
          a carrier filling one will want the other in the same place. */}
      <MeetingPlacesSection />
      <StandingNoteSection
        titleKey="rules.payment.title"
        descKey="rules.payment.desc"
        fields={[
          {
            name: 'payment_instructions',
            labelKey: 'rules.payment.label',
            descKey: 'rules.payment.labelDesc',
            placeholderKey: 'rules.payment.placeholder',
          },
        ]}
        /* T3.11.07 — the shortlist lives inside this card rather than beside
           it: «как со мной рассчитаться» is one question, and two headings for
           it would make the chips look like a different subject. */
        extra={<PaymentMethodsField />}
      />
    </div>
  )
}
