import { useTranslation } from 'react-i18next'
import type { DealDetail } from '../api/deals'
import type { Terms } from '../api/terms'
import { usePrefs } from '../hooks/usePrefs'
import MonoText from './MonoText'

interface Props {
  deal: DealDetail
  terms: Terms | null
  /** Open while the agreement is not confirmed by both — the first stage *is*
   *  agreeing it, and a collapsed card there would be an empty screen. */
  open: boolean
  onToggle: () => void
}

/** T3.11.27 — the deal card, which is what the boarding pass became.
 *
 *  Owner's decision 2026-09-07: «Карточка сделки должна быть заменой
 *  Посадочному талону, который показывается в свёрнутом виде». Collapsed it
 *  shows the header — route, date, parties, number, price; expanded it shows the
 *  four sections the two sides actually negotiate.
 *
 *  **The header is not one of the sections and never becomes editable.** Route,
 *  flight date, who is who and the shipment number are facts of the trip and of
 *  the deal's identity; the sections below are the agreement. Putting them in
 *  one list would have made «изменены условия» able to mean «the flight moved»,
 *  which is a different event with its own notice (`T3.11.16`).
 *
 *  Functions (PROJECT §6.2a):
 *  - `DealAgreementCard({ deal, terms, open, onToggle })` — default export.
 *    Called by: `pages/DealVaultPage`.
 */
export default function DealAgreementCard({ deal, terms, open, onToggle }: Props) {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const p = terms?.payload ?? {}

  /** One line of a section, drawn only when there is something to say. A field
   *  nobody answered is left out rather than printed as a dash: «не сказал» and
   *  «сказал, что нет» are different answers, and the whole deal model stands on
   *  keeping them apart. */
  const row = (label: string, value: React.ReactNode) =>
    value === null || value === undefined || value === '' ? null : (
      <div key={label} className="flex justify-between gap-4 py-0.5">
        <span className="text-xs font-body text-navy/45">{label}</span>
        <span className="text-xs font-body text-navy text-right">{value}</span>
      </div>
    )

  const section = (key: string, rows: React.ReactNode[]) => {
    const filled = rows.filter(Boolean)
    if (filled.length === 0) return null
    const locked = (p.locked ?? []).includes(key)
    return (
      <div key={key} className="border-t border-navy/10 pt-2">
        <div className="flex items-center gap-2 mb-1">
          <h4 className="text-[11px] font-display font-semibold text-navy/45 uppercase tracking-wide">
            {t(`agreement.section.${key}`)}
          </h4>
          {/* A locked section is the carrier's: «I carry it this way or not at
              all». Named on the card so the other side knows before they try. */}
          {locked && (
            <span className="text-[10px] font-mono text-navy/40">
              🔒 {t('agreement.locked')}
            </span>
          )}
        </div>
        {filled}
      </div>
    )
  }

  const method = (m: string | null | undefined) =>
    m ? t(`cards.opt.${m}`, m) : null

  return (
    <div className="rounded-field border border-navy/10 bg-white">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full text-left px-3 py-2 hover:bg-ivory transition-colors rounded-field"
      >
        <div className="flex items-center justify-between gap-3">
          <MonoText className="text-sm text-navy font-medium">
            {deal.origin} → {deal.destination}
          </MonoText>
          <MonoText className="text-xs text-navy/40">{open ? '▾' : '▸'}</MonoText>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
          <MonoText className="text-xs text-navy/50">
            {prefs.dateTime(deal.depart_at)}
          </MonoText>
          {p.price_total != null && (
            <MonoText className="text-xs text-navy">
              {p.price_total} {p.currency ?? prefs.currency}
            </MonoText>
          )}
          {deal.shipment_no && (
            <MonoText className="text-xs text-navy/50">
              № {deal.shipment_no}
            </MonoText>
          )}
          <span className="text-xs font-body text-navy/45">
            {deal.sender_name} → {deal.carrier_name}
          </span>
        </div>
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2">
          {terms === null ? (
            <p className="text-xs font-body text-navy/45 border-t border-navy/10 pt-2">
              {t('agreement.empty')}
            </p>
          ) : (
            <>
              {section('cargo', [
                row(t('agreement.field.what'), p.cargo_what),
                row(
                  t('agreement.field.weight'),
                  p.weight_kg != null ? prefs.weight(p.weight_kg) : null,
                ),
                row(
                  t('agreement.field.declared'),
                  p.declared_value != null
                    ? `${p.declared_value} ${p.currency ?? ''}`.trim()
                    : null,
                ),
                row(t('agreement.field.packaging'), p.cargo_packaging),
                row(
                  t('agreement.field.fragile'),
                  p.cargo_fragile ? t('common.yes') : null,
                ),
                row(
                  t('agreement.field.openOnHandover'),
                  p.cargo_open_on_handover ? t('common.yes') : null,
                ),
                row(
                  t('agreement.field.url'),
                  p.cargo_url ? (
                    <a
                      href={p.cargo_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-cyan hover:underline break-all"
                    >
                      {p.cargo_url}
                    </a>
                  ) : null,
                ),
              ])}
              {section('handover', [
                row(t('agreement.field.method'), method(p.handover_method)),
                row(t('agreement.field.place'), p.handover_place),
                row(
                  t('agreement.field.at'),
                  p.handover_at ? prefs.dateTime(p.handover_at) : null,
                ),
              ])}
              {section('delivery', [
                row(t('agreement.field.method'), method(p.delivery_method)),
                row(t('agreement.field.place'), p.delivery_place),
                row(
                  t('agreement.field.at'),
                  p.delivery_at ? prefs.dateTime(p.delivery_at) : null,
                ),
              ])}
              {section('payment', [
                row(
                  t('agreement.field.price'),
                  p.price_total != null
                    ? `${p.price_total} ${p.currency ?? ''}`.trim()
                    : null,
                ),
                row(
                  t('agreement.field.method'),
                  p.payment_method
                    ? t(`cards.opt.${p.payment_method}`, p.payment_method)
                    : null,
                ),
                row(
                  t('agreement.field.payer'),
                  p.payer ? t(`agreement.payer.${p.payer}`) : null,
                ),
              ])}
              {deal.carriage_rules && (
                <div className="border-t border-navy/10 pt-2">
                  <h4 className="text-[11px] font-display font-semibold text-navy/45 uppercase tracking-wide mb-1">
                    {t('deals.carriageRules')}
                  </h4>
                  <p className="text-xs font-body text-navy/70 whitespace-pre-wrap">
                    {deal.carriage_rules}
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
