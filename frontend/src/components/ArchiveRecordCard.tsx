import { useTranslation } from 'react-i18next'
import type { ArchiveRecord } from '../api/trust'
import MonoText from './MonoText'

/**
 * T3.19 — the placard under a retired identity.
 *
 * Retiring is a change of genre, not a death: the account stops being able to
 * act and becomes a historical document. What it signed while the key lived is
 * untouched by the key's loss — those two things are independent here for the
 * first time, and this card is the second one.
 *
 * Three rules the markup enforces, not just the copy:
 *
 * 1. **Every total is shown with the set it was counted from.** "12 closed" on
 *    its own invites the reader to supply a denominator; "12 of 15" does not.
 * 2. **A number that could not be measured is absent, not zero.** A confident
 *    "0 km" for routes we could not resolve claims a measurement that never
 *    happened.
 * 3. **Distances say "straight line" in the label, every time.** The value is a
 *    great-circle arc between two airports; real tracks run longer, and this
 *    measures where a parcel went rather than what an aircraft flew.
 *
 * Not written here, deliberately: "verified forever". The chain is
 * tamper-evident, not tamper-proof, and the phrasing that would be true —
 * independently checkable as of the last anchor — needs anchors switched on
 * (T3.20). Until then the card says what it can prove and stops there.
 */
export default function ArchiveRecordCard({
  record,
  memberSince,
}: {
  record: ArchiveRecord
  memberSince?: string | null
}) {
  const { t, i18n } = useTranslation()
  const date = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleDateString(i18n.language) : '—'
  const number = (value: number) => value.toLocaleString(i18n.language)

  return (
    <div
      data-testid="archive-record"
      className="bg-navy/5 rounded-card border border-navy/10 p-5 space-y-4"
    >
      <div>
        <h2 className="font-display font-semibold text-base text-navy">
          {t('archive.title')}
        </h2>
        <p className="text-sm font-body text-navy/60 mt-1">
          {memberSince
            ? t('archive.period', {
                from: date(memberSince),
                to: date(record.retired_at),
              })
            : t('archive.retiredOn', { date: date(record.retired_at) })}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm font-body">
        <div>
          <dt className="text-xs text-navy/50">{t('archive.deals')}</dt>
          <dd className="text-navy">
            {t('archive.ofTotal', {
              part: number(record.deals_closed),
              total: number(record.deals_total),
            })}
          </dd>
        </div>
        <div>
          {/* A chain entry with no Nostr signature is a real event in a real
              chain — calling it a signature would claim a proof the row does
              not carry, so both numbers are shown. */}
          <dt className="text-xs text-navy/50">{t('archive.signatures')}</dt>
          <dd className="text-navy">
            {t('archive.ofEntries', {
              part: number(record.signatures),
              total: number(record.chain_entries),
            })}
          </dd>
        </div>
        {record.last_signature_at && (
          <div>
            <dt className="text-xs text-navy/50">{t('archive.lastSignature')}</dt>
            <dd className="text-navy">
              <MonoText className="text-sm">{date(record.last_signature_at)}</MonoText>
            </dd>
          </div>
        )}
        {record.first_signature_at && (
          <div>
            <dt className="text-xs text-navy/50">{t('archive.firstSignature')}</dt>
            <dd className="text-navy">
              <MonoText className="text-sm">{date(record.first_signature_at)}</MonoText>
            </dd>
          </div>
        )}
        {record.straight_line_km !== null && (
          <div>
            <dt className="text-xs text-navy/50">{t('archive.straightLineKm')}</dt>
            <dd className="text-navy">
              <MonoText className="text-sm">{number(record.straight_line_km)}</MonoText>
              <span className="block text-xs text-navy/40">
                {t('archive.measuredOn', {
                  part: number(record.routes_measured),
                  total: number(record.routes_closed),
                })}
              </span>
            </dd>
          </div>
        )}
        {record.longest_hop_km !== null && (
          <div>
            {/* The record, not the mean: in a museum the outlier is the
                exhibit, and an average of four routes says nothing. */}
            <dt className="text-xs text-navy/50">{t('archive.longestHop')}</dt>
            <dd className="text-navy">
              <MonoText className="text-sm">{number(record.longest_hop_km)}</MonoText>
              {record.longest_hop_route && (
                <span className="block text-xs font-mono text-navy/40">
                  {record.longest_hop_route}
                </span>
              )}
            </dd>
          </div>
        )}
        {record.rarest_corridor && (
          <div>
            {/* Rarity is a property of the route. The trip count travels with
                it so the line cannot be read as "this person is rare". */}
            <dt className="text-xs text-navy/50">{t('archive.rarestCorridor')}</dt>
            <dd className="text-navy">
              <MonoText className="text-sm">{record.rarest_corridor}</MonoText>
              {record.rarest_corridor_trips !== null && (
                <span className="block text-xs text-navy/40">
                  {t('archive.corridorTrips', { count: record.rarest_corridor_trips })}
                </span>
              )}
            </dd>
          </div>
        )}
        {record.capacity_kg !== null && (
          <div>
            <dt className="text-xs text-navy/50">{t('archive.capacityKg')}</dt>
            <dd className="text-navy">
              <MonoText className="text-sm">{number(record.capacity_kg)}</MonoText>
              <span className="block text-xs text-navy/40">
                {t('archive.tripsCompleted', { count: record.trips_completed })}
              </span>
            </dd>
          </div>
        )}
      </dl>

      {/* T3.20 — the strongest sentence this card is allowed to say, and only
          when an anchor exists. Anchoring puts a chain head on relays we do not
          control; everything beneath it is fixed by someone else's clock, and
          everything after it is not. So the claim carries a date and a count,
          and disappears entirely when there is nothing behind it. */}
      {record.last_anchor_at && (
        <p
          data-testid="archive-anchor"
          className="text-xs font-body text-navy/60 border-t border-navy/10 pt-3"
        >
          {t('archive.anchoredAsOf', {
            date: date(record.last_anchor_at),
            part: number(record.anchored_deals),
            total: number(record.deals_total),
          })}
        </p>
      )}

      <p className="text-xs font-body text-navy/50 border-t border-navy/10 pt-3">
        {t('archive.footnote')}
      </p>
    </div>
  )
}
