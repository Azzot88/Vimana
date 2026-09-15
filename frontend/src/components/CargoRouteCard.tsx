import { useTranslation } from 'react-i18next'
import type { DealDetail } from '../api/deals'
import MonoText from './MonoText'

interface Props {
  deal: DealDetail
}

/** T3.12.10 — the cargo's route above the deal (`IMPLEMENTATIONPLAN §3.12.7`).
 *
 *  Owner, 2026-09-15: a route card — the shipment number, the line from one end
 *  to the other, and this deal named on it. A single deal fills the whole line,
 *  and that is not decoration: it is the place the next deals stand in when a
 *  cargo travels through more than one (`D-CARGO-MODEL`). The mechanics of
 *  multi-hop are deliberately not in this phase, so the card draws what the
 *  deal itself knows rather than fetching a chain that does not exist yet.
 *
 *  Where the cargo is comes from the server (`cargo_location`), read off the
 *  deal's status: the screen does not compute a second answer to that question.
 *
 *  Functions (PROJECT §6.2a):
 *  - `CargoRouteCard({ deal })` — default export.
 *    Called by: `pages/DealVaultPage`.
 */
export default function CargoRouteCard({ deal }: Props) {
  const { t } = useTranslation()
  const number = deal.deal_no ?? deal.shipment_no

  return (
    <div className="rounded-field border border-navy/10 bg-white px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="text-[11px] font-display font-semibold text-navy/45 uppercase tracking-wide">
          {t('cargoRoute.title')}
        </h3>
        {number && (
          <MonoText className="text-xs text-navy/60">№ {number}</MonoText>
        )}
        {deal.cargo_location && (
          <span className="text-xs font-body text-navy/45 ml-auto">
            {t(`cargoRoute.where.${deal.cargo_location}`, deal.cargo_location)}
          </span>
        )}
      </div>

      {/* The line itself: both ends named, this deal on the leg between them.
          `multihop` says the cargo has more legs than this one — until their
          mechanics land, it is said in words rather than drawn as points
          nobody can open. */}
      <div className="mt-1.5 flex items-center gap-2">
        <MonoText className="text-sm text-navy font-medium">{deal.origin}</MonoText>
        <span className="flex-1 h-px bg-cyan/50" aria-hidden="true" />
        <span className="text-[11px] font-body text-cyan whitespace-nowrap">
          {t('cargoRoute.thisDeal')}
        </span>
        <span className="flex-1 h-px bg-cyan/50" aria-hidden="true" />
        <MonoText className="text-sm text-navy font-medium">
          {deal.destination}
        </MonoText>
      </div>

      {deal.multihop && (
        <p className="text-[11px] font-body text-navy/45 mt-1">
          {t('cargoRoute.multihop')}
        </p>
      )}
    </div>
  )
}
