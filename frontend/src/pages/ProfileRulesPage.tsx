import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import AddressesSection from '../components/AddressesSection'
import StandingNoteSection from '../components/StandingNoteSection'

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
      <AddressesSection />
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
      />
    </div>
  )
}
