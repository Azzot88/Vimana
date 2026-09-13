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
  | 'arrived'
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
  /** T3.11.27 — **gone, and deliberately left named here.** (owner, 2026-09-12)
   *
   *  A stage used to own a photograph: an upload button beside the buttons, one
   *  picture, filed as its own chat row. Two rounds of the same defect killed
   *  it. First «фото должно отправляться вместе со статусом» — every custody
   *  card declares `requires_attachment` and the server refuses to let the other
   *  side confirm a declaration with no evidence, so a photograph uploaded
   *  beside the card left that card permanently unconfirmable while the picture
   *  sat three lines above it. Then «фото должно быть внутри формы Предложить
   *  условия», which took the last one — «вот что я отправляю» — into the
   *  proposal, where it can also be several.
   *
   *  Every photograph in a deal now hangs on the act it is evidence for. If a
   *  stage ever needs one again, it needs a card first. */
  photo?: never
  photoBy?: never
}

/** The whole ladder, in order. `closed` is last and has nothing to do — it is
 *  there so the strip can show the deal as finished rather than as stuck on
 *  payment forever. */
export const DEAL_STAGES: DealStage[] = [
  {
    key: 'terms',
    statuses: ['draft', 'matched'],
    /* T3.11.27 (owner, 2026-09-12): «Кнопка условия передачи и Способ оплаты и
       фото должны быть внутри формы Предложить условия, открываться внутри и
       вместе отправляться в чат.»

       Both used to stand here as chips beside the form: three separate acts
       producing three separate cards about one agreement, two of which asked
       again for fields the form already had. They are sections of the proposal
       now. `payment.method_agreed` stays in the catalogue — «модель может быть
       изменена по обоюдному согласию» — but it is a later correction, not a
       step of the first stage, so it is not offered here. */
    kinds: [],
  },
  {
    key: 'handover',
    statuses: ['accepted'],
    kinds: ['pickup.proposed', 'handoff.declared', 'handoff.received'],
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
  },
  {
    /* T3.11.27 (owner, 2026-09-12): «разделить статусы Вылетел В Пути и
       Прилетел на два экрана. То есть это дополнительный информационный шаг для
       всех участников.»

       Landing is the moment the recipient's side of the deal starts: it is when
       «когда забирать» stops being a plan and becomes a time. One rung called
       «В пути» covered a flight, a landing and a day of waiting for a call, so
       three different situations looked identical on the ladder.

       **Not a deal status, on purpose.** The server moves `Deal.status` on
       acceptances — two people saying a thing happened — and nobody
       countersigns a landing. It is the carrier's own `transit.update` with
       `stage: arrived`, which is already a card in the chain; this stage simply
       reads it. Inventing a status for it would mean a transition nobody can
       answer and a second record of where the parcel is. */
    key: 'arrived',
    statuses: ['in_transit'],
    kinds: ['dropoff.proposed', 'delivery.declared'],
  },
  {
    key: 'delivery',
    statuses: ['posted', 'delivered'],
    kinds: [],
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

/** T3.11.27 — what the status alone cannot say.
 *
 *  `arrived` is the one rung that is not a status: it is the carrier's own
 *  `transit.update` saying the flight landed. Passed in rather than looked up
 *  here, because this module deliberately knows nothing about messages — it
 *  maps a status to a stage and that is all it has ever done. */
export interface StageMarks {
  arrived?: boolean
}

export function stageOf(
  status: DealStatus,
  marks: StageMarks = {},
): DealStageKey {
  if (status === 'disputed') return 'delivery'
  // T3.11.27 — a cancelled deal stands at the end of the ladder without having
  // walked it. Not a stage of its own: the strip shows how far a delivery got,
  // and a stage nobody can ever be on would be a rung nobody climbs.
  if (status === 'cancelled') return 'closed'
  const found = DEAL_STAGES.find((s) => s.statuses.includes(status))
  if (found?.key === 'transit' && marks.arrived) return 'arrived'
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
