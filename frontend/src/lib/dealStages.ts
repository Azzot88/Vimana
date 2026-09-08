import type { AttachmentKind } from '../api/dealvault'
import type { DealStatus } from '../api/deals'
import type { DealRole } from './cardForms'

/** T3.11.17 — the deal as a ladder of stages, not a wall of buttons.
 *
 *  Owner's decision 2026-09-07: the actions appear **in turn**, following the
 *  stage the deal is actually on. Until the terms are fixed there is no handover
 *  to arrange, so offering it is offering a step nobody can take — and nine
 *  chips at once made the two that mattered indistinguishable from the seven
 *  that did not.
 *
 *  The ladder is derived from `Deal.status`, which the server moves through card
 *  acceptances. Nothing here decides anything: this module says which stage a
 *  status *is*, and the screen draws it. A second source of truth about where a
 *  deal stands is the thing this file exists to avoid.
 *
 *  Functions (PROJECT §6.2a):
 *  - `stageOf(status)` — the stage a deal is standing on.
 *    Called by: `components/DealStages`.
 *  - `stagesFor(role)` — the ladder as one role sees it, in order.
 *    Called by: `components/DealStages`.
 */
export type DealStageKey =
  | 'terms'
  | 'handover'
  | 'transit'
  | 'delivery'
  | 'payment'
  | 'closed'

export interface DealStage {
  key: DealStageKey
  /** Statuses that mean the deal is standing here. */
  statuses: DealStatus[]
  /** Card kinds offered at this stage, in the order they are meant to happen.
   *  Filtered again by role inside `CardActions` — a stage says *when*, a role
   *  says *who*. */
  kinds: string[]
  /** The photograph this stage is about, if it is about one. Preselected rather
   *  than chosen from a dropdown: at a handover the picture is of the handover,
   *  and asking which kind it is at the moment somebody is holding a parcel and
   *  a phone is a question with one answer. */
  photo?: AttachmentKind
  /** Roles that may attach that photo. The others see the stage without an
   *  upload button rather than an upload that is refused. */
  photoBy?: DealRole[]
}

/** The whole ladder, in order. `closed` is last and has nothing to do — it is
 *  there so the strip can show the deal as finished rather than as stuck on
 *  payment forever. */
export const DEAL_STAGES: DealStage[] = [
  {
    key: 'terms',
    statuses: ['draft', 'matched'],
    // Terms themselves are raised by their own form (the price is the one thing
    // worth a screen of its own), so what is left here is what else has to be
    // agreed before anything moves.
    kinds: ['handover.conditions', 'payment.method_agreed'],
  },
  {
    key: 'handover',
    statuses: ['accepted'],
    kinds: ['pickup.proposed', 'handoff.declared'],
    photo: 'handoff_photo',
    photoBy: ['sender'],
  },
  {
    key: 'transit',
    statuses: ['in_transit'],
    kinds: [
      'transit.update',
      'dropoff.proposed',
      'posted.declared',
      'delivery.declared',
    ],
    // T3.11.17 — the parcel photographed before it was sealed. The carrier is
    // the one at the post office, so it is theirs to attach.
    photo: 'pre_seal_photo',
    photoBy: ['carrier'],
  },
  {
    key: 'delivery',
    statuses: ['posted', 'delivered'],
    kinds: [],
    photo: 'receipt_photo',
    photoBy: ['carrier', 'recipient'],
  },
  {
    key: 'payment',
    // Owner's decision 2026-09-07: the method is agreed with the price, and the
    // money is the last stage. It shares its statuses with delivery because on
    // this market the two overlap — cash changes hands at the door — and the
    // screen shows both rather than pretending one waits for the other.
    statuses: ['posted', 'delivered'],
    kinds: ['payment.declared'],
  },
  { key: 'closed', statuses: ['confirmed', 'closed'], kinds: [] },
]

/** Never gated by stage: a problem and a cancellation are needed exactly when
 *  something has gone off the ladder. Hidden behind «ещё» (owner's decision
 *  2026-09-07) — always reachable, never in the way. */
export const ALWAYS_AVAILABLE = ['issue.reported', 'cancel.requested']

/** T3.11.27 — nothing is left to do on these, and `ALWAYS_AVAILABLE` is hidden
 *  for them: offering «запросить отмену» on a deal already cancelled is a
 *  control that can only fail. */
export const TERMINAL_STATUSES: DealStatus[] = ['confirmed', 'closed', 'cancelled']

export function stageOf(status: DealStatus): DealStageKey {
  if (status === 'disputed') return 'delivery'
  // T3.11.27 — a cancelled deal stands at the end of the ladder without having
  // walked it. Not a stage of its own: the strip shows how far a delivery got,
  // and a stage nobody can ever be on would be a rung nobody climbs.
  if (status === 'cancelled') return 'closed'
  const found = DEAL_STAGES.find((s) => s.statuses.includes(status))
  return found ? found.key : 'terms'
}

/** How far down the ladder this deal has come. Used to draw what is done, what
 *  is now and what is still ahead — the «список смены статусов» the owner
 *  asked for, read off the status rather than kept as a second record. */
export function stageIndex(key: DealStageKey): number {
  return DEAL_STAGES.findIndex((s) => s.key === key)
}

/** The stages worth drawing for a role. `payment` and `delivery` share statuses,
 *  so both are live at once late in a deal; the strip still shows them in
 *  order, because that is the order they are meant to happen in. */
export function stagesFor(_role: DealRole | null): DealStage[] {
  return DEAL_STAGES
}
