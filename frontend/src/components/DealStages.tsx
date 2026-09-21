import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { DealDetail, DealStatus } from '../api/deals'
import { DISPUTE_REASONS, openDispute, type DisputeReason } from '../api/admin'
import { raiseCard } from '../api/terms'
import type { VaultMessage } from '../api/dealvault'
import {
  ALWAYS_AVAILABLE,
  DEAL_STAGES,
  TERMINAL_STATUSES,
  stageIndex,
  stageOf,
  type DealStageKey,
} from '../lib/dealStages'
import type { Terms } from '../api/terms'
import { formsForRole, type DealRole } from '../lib/cardForms'
import CardActions from './CardActions'
import { usePrefs } from '../hooks/usePrefs'
import MeetingNote, { meetingOf } from './MeetingNote'
import HandoverNote from './HandoverNote'
import StorageNote from './StorageNote'
import TermsProposeForm from './TermsProposeForm'

interface Props {
  dealId: string
  status: DealStatus
  myRole: DealRole | null
  /** The agreement as it stands: `null` before anybody proposes anything. The
   *  first stage is not over until it is agreed, and nothing below it should be
   *  offered before that. */
  terms: Terms | null
  /** T3.11.27 — the deal as the board form left it. Used to open the first
   *  version of the agreement already filled in; ignored once there is an
   *  agreement to edit, which is the sharper source. */
  deal: DealDetail | null
  /** T3.11.27 — what has already been said in this deal. Read for one thing
   *  only: a card of some kind is standing unanswered, so the button that
   *  raises that kind is not offered again. */
  messages: VaultMessage[]
  onDone: () => void
}

/** T3.11.17 — the left-hand side of a deal: where it stands, and what to do next.
 *
 *  Owner's decision 2026-09-07: the actions appear **in turn**, following the
 *  stage. Nine chips at once put «согласовать условия» and «запросить отмену»
 *  side by side as equals, so the screen said everything and therefore nothing.
 *  Now one stage is live, its actions are the only ones drawn at full weight,
 *  and the ladder above shows what is done and what is still ahead.
 *
 *  **Nothing here decides the stage.** `Deal.status` does, and the server moves
 *  it through card acceptances; this component reads it. A screen that worked
 *  out the stage for itself would be a second opinion about where a deal stands,
 *  and the two would disagree on the day it mattered.
 *
 *  **No photograph belongs to a stage** (T3.11.27, 2026-09-12). Every picture in
 *  a deal hangs on the act it is evidence for — the custody photos on their
 *  cards, «вот что я отправляю» on the proposal. A panel that could file one
 *  beside an act instead of on it is what left cards unconfirmable with their
 *  own evidence three lines above them.
 *
 *  **The arbiter lives here too** (T3.11.27). It used to sit in `DealPage`,
 *  which is now rendered folded inside «Ещё о сделке» — an accordion whose own
 *  label says it holds background. «Спор как этап вклинивается в сделку на
 *  любом моменте» (owner, 2026-09-07): an action for any moment cannot be two
 *  clicks and a scroll away, and least of all at the one moment it is most
 *  needed — a parcel handed over and no money.
 *
 *  Functions (PROJECT §6.2a):
 *  - `DealStages({...})` — default export. Called by: `pages/DealVaultPage`.
 */
export default function DealStages({
  dealId,
  status,
  myRole,
  terms,
  deal,
  messages,
  onDone,
}: Props) {
  const { t } = useTranslation()
  const [termsOpen, setTermsOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  // T3.11.27 — the arbiter moved here from «Ещё о сделке». Owner's rule
  // 2026-09-07: «Спор как этап вклинивается в сделку на любом моменте» and
  // «Отдано, но не оплачено — доступно "Пригласить арбитра"». It was behind a
  // collapsed accordion whose own label says it holds background — which is the
  // wrong place for the one action somebody takes when the ladder has stopped
  // describing what is happening.
  const [disputeOpen, setDisputeOpen] = useState(false)
  const [disputeReason, setDisputeReason] = useState<DisputeReason>('unpaid')
  const [disputeDetails, setDisputeDetails] = useState('')
  const [disputeBusy, setDisputeBusy] = useState(false)
  // T_UX.28 п.7 — the arrival and the meeting are shown in the reader's own
  // date settings, like every other moment on this screen.
  const prefs = usePrefs()
  const [disputeError, setDisputeError] = useState('')
  /* T3.12.05 — the same form, sent as a request to the sender rather than as a
     dispute: the recipient does not open one, they ask (owner, 2026-09-13/14). */
  const asking = myRole === 'recipient'

  /* T3.11.27 — the landing, read off the card that announced it (owner,
     2026-09-12). A `transit.update` with `stage: arrived` is the carrier
     saying the flight is down; it is already in the chain, so the ladder reads
     it rather than keeping a second record. Superseded and declined updates
     count too: the plane landed either way, and a correction to the ETA does
     not un-land it. */
  const arrived = messages.some(
    (m) =>
      m.card_kind === 'transit.update' &&
      (m.card_payload as { stage?: string } | null)?.stage === 'arrived',
  )
  // T3.12.08 — and whether it went by post, which is what keeps a paid-but-not
  // -received deal standing on delivery instead of reading as closed.
  const posted = messages.some((m) => m.card_kind === 'posted.confirmed')
  /* T_UX.28 п.6 — every journey status already declared here, so the form can
     stop offering the ones that cannot be pressed again. Read off the same
     cards the ladder reads: a second list of «где посылка» is a second thing
     to be wrong. */
  const doneStages = messages
    .filter((m) => m.card_kind === 'transit.update')
    .map((m) => (m.card_payload as { stage?: string } | null)?.stage)
    .filter((stage): stage is string => typeof stage === 'string')

  /* T_UX.29 pt.2 п.1, п.3 (owner, 2026-09-20): «После смены статуса "Прилетел"
     на "Таможня" окно не обновилось» и «Статус хранение должен показывать
     получателю, что можно планировать забор посылки».

     Where the parcel is **right now**, as the carrier last declared it. Two
     complaints with one answer: pressing a chip changed nothing on the panel —
     the news went into the chat and the left-hand column stood as it was — and
     the person waiting for the parcel had nowhere to read what «таможня» or
     «хранение» means for them. Neither is a rung: customs, delay and storage
     come round more than once, and a rung that repeats stops being a rung
     (`T_DEAL.1`). So they are a line under the heading, with the sentence that
     says what to do about them.

     The **last** declaration wins, not the furthest milestone: a parcel that
     landed and then went into storage is in storage. Superseded and declined
     cards count for the same reason the landing does — the carrier said it. */
  const lastTransit = [...messages]
    .reverse()
    .map((m) =>
      m.card_kind === 'transit.update'
        ? (m.card_payload as { stage?: string } | null)?.stage
        : undefined,
    )
    .find((stage): stage is string => typeof stage === 'string')

  /* Silent on the two that are rungs of their own: «Сейчас: Прилетел» under a
     heading reading «Прилетел» is a line that repeats rather than informs. */
  const transitNow =
    lastTransit && lastTransit !== 'arrived' && lastTransit !== 'departed'
      ? lastTransit
      : null
  const transitHint = transitNow
    ? t(`stages.transitHint.${transitNow}`, { defaultValue: '' })
    : ''

  const marks = { arrived, posted }
  const currentKey: DealStageKey = stageOf(status, marks)
  const currentIndex = stageIndex(currentKey)

  /* T_UX.28 п.7 (owner, 2026-09-19): «На странице статуса всегда должна быть
     информация о следующем запланированном статусе. Если вылетел, то надо
     писать когда прилёт и куда. Если прилетел, то надо давать инфу о
     предстоящей встрече и где. Эти данные все есть, их надо показывать.»

     They were all there and none of them were here: the arrival sat on the
     trip's last segment, which the deal screen never asked the server for, and
     the meeting sat in the agreement, which this panel reads for the buttons
     rather than for the sentence above them.

     Below `currentKey` on purpose — it is the stage that decides which of the
     two facts is the next one — and silent when there is nothing to say: an
     empty «Дальше:» reads as a step nobody planned rather than as data we do
     not have. */
  const segments = (deal?.trip_segments ?? [])
    .slice()
    .sort((a, b) => a.order - b.order)
  // Indexed rather than `.at(-1)`: this project builds to ES2020.
  const lastSegment = segments.length > 0 ? segments[segments.length - 1] : null
  const nextStep = (() => {
    if (status === 'cancelled' || TERMINAL_STATUSES.includes(status)) return null
    if (currentKey === 'transit' && lastSegment) {
      const place = lastSegment.destination_city || lastSegment.destination
      return lastSegment.arrive_at
        ? t('stages.next.arrival', {
            place,
            when: prefs.dateTime(lastSegment.arrive_at),
          })
        : t('stages.next.arrivalNoTime', { place })
    }
    const side = currentKey === 'handover' ? 'handover' : 'delivery'
    const meeting = meetingOf(terms, messages, side)
    if (!meeting.place) return null
    const key = side === 'handover' ? 'meeting' : 'delivery'
    return meeting.at
      ? t(`stages.next.${key}`, {
          place: meeting.place,
          when: prefs.dateTime(meeting.at),
        })
      : t(`stages.next.${key}NoTime`, { place: meeting.place })
  })()

  const raiseDispute = async () => {
    setDisputeBusy(true)
    setDisputeError('')
    try {
      if (asking) {
        await raiseCard(
          dealId,
          'dispute.requested',
          { reason: disputeReason },
          disputeDetails.trim() || undefined,
        )
      } else {
        await openDispute(dealId, disputeReason, disputeDetails.trim() || undefined)
      }
      setDisputeOpen(false)
      setDisputeDetails('')
      onDone()
    } catch {
      setDisputeError(t('dispute.openError'))
    } finally {
      setDisputeBusy(false)
    }
  }

  /* T3.11.27 — «Отдано, но не оплачено» (owner, 2026-09-07). The parcel is with
     the person it was for and the money has not been settled: the one moment
     the arbiter stops being a last resort and becomes the next step. Named on
     the panel rather than left to be found, because somebody in this position
     is already unsure whether they are allowed to complain. */
  /* T3.12.01 — not the recipient. The server refuses them (`api/admin.
     open_dispute`), and the owner's rule is that the recipient asks the sender
     to open it (`T3.12.05`): a button drawn only to be refused is worse than
     none. */
  const mayDispute = Boolean(myRole) && myRole !== 'recipient'

  const handedOverUnpaid =
    (status === 'delivered' || status === 'posted') && mayDispute

  const canDispute =
    mayDispute &&
    ['accepted', 'in_transit', 'posted', 'delivered'].includes(status)

  /* T3.11.27 — «Плательщик определён на этапе условий, поэтому
     получатель-неплательщик жмёт только "Получил", а деньги закрывает тот, кто
     по карточке платит» (owner, 2026-09-07).

     The server reads the same field and refuses anybody else with a 403, so
     this is not a permission check — it is the difference between a screen that
     offers one button and a screen that offers two, one of which always fails.
     Defaults to the sender: that is the field's own default and the shape of
     every deal agreed before the section existed. */
  const payer = terms?.payload?.payer ?? 'sender'
  /* Narrowed twice, and both narrowings matter. By the agreement, because only
     the named payer may declare money; and by role, because most cards belong
     to one side — `handoff.declared` is the sender's, `transit.update` the
     carrier's. `CardActions` filters by role again internally; doing it here as
     well is what lets the panel tell «нечего нажимать» apart from «сейчас не
     твой ход», which are different things to say and were both drawn as an
     empty space. */
  /* T3.11.27 (owner, walking the flow 2026-09-12): «Нет кнопки Сколько денег
     получено и подтверждения получения. Но сделка закрылась.»

     Here is why there was no button. `delivery` and `payment` deliberately
     **share** their statuses — on this market the cash changes hands at the
     door, so the two stages overlap and `dealStages` says in as many words that
     «the screen shows both rather than pretending one waits for the other». The
     screen did not: `stageOf` returns one key and `find` stops at the first
     match, which is `delivery`, whose `kinds` are empty. So at `posted` and
     `delivered` the panel offered nothing at all, and the only way a deal could
     end was the one-press close — which is exactly the pair of symptoms the
     owner reported together.

     Every stage standing on this status is live, not just the first one. */
  /* T_UX.29 п.3 — and a stage that is waiting for something is not live yet.
     `arrived` shares `in_transit` with `transit`, so the union above made the
     whole arrival — «Отправлено по почте», «Передано в доставку» — pressable
     over a parcel still in the air. `delivery` and `payment` declare no mark
     and go on overlapping, which is the case this union was written for. */
  const liveKinds = Array.from(
    new Set(
      DEAL_STAGES.filter(
        (s) =>
          s.key === currentKey ||
          (s.statuses.includes(status) && (!s.requires || marks[s.requires])),
      ).flatMap((s) => s.kinds),
    ),
    /* T3.12.08 — «получено как должно» exists only for a posted parcel: at
       `posted`, or `confirmed` when the carrier was paid first. Filtered here,
       not below, so a closed or hand-delivered deal does not read as «ход
       второй стороны» over a card nobody can raise. */
  ).filter(
    (kind) =>
      kind !== 'received.as_expected' || status === 'posted' || status === 'confirmed',
  )
  /* T3.12.07 — on the receiving side the person at the door declares the
     handover. With a separate recipient that is not the sender, and the server
     refuses them; the button is not drawn for a refusal. */
  const separateRecipient =
    Boolean(deal?.recipient_id) && deal?.recipient_id !== deal?.sender_id
  const stageKinds = liveKinds.filter(
    (kind) =>
      (kind !== 'payment.declared' || myRole === payer) &&
      (kind !== 'delivery.declared' || myRole !== 'sender' || !separateRecipient) &&
      // T3.12.08 — the sender receives only when nobody else does.
      (kind !== 'received.as_expected' || myRole !== 'sender' || !separateRecipient),
  )
  /* T3.11.27 (owner, 2026-09-12): «После того как нажата кнопка Передал
     перевозчику она должна пропадать сразу… Она должна появляться только если
     Перевозчик не подтвердил получение, тогда откатывается назад на один шаг.»

     The button was drawn from the deal's **status**, and the status does not
     move until the other side confirms — so after declaring a handover the
     sender kept looking at «Передал перевозчику» and could declare it again,
     and again. The stage is the right source for *when* an action is possible;
     it cannot know that this particular one has already been taken.

     A standing card is what says so. Raising a second one while the first is
     unanswered would put two contradictory declarations of the same act in the
     chain, which is precisely the record an arbiter cannot read. Declined and
     superseded cards are not pending, so a refusal brings the button straight
     back — that is the «откат на один шаг», and it needs no state of its own:
     the poll brings the refusal and the button reappears with it. */
  const pendingKinds = new Set(
    messages
      .filter((m) => m.card_state === 'pending' && m.card_kind)
      .map((m) => m.card_kind as string),
  )
  /* T_UX.28 (owner, 2026-09-16) — «Перенести вручение» is the right words only
     when there is something to move. The first time nothing has been arranged,
     and a button offering to move it reads as though somebody already had. The
     same arrangement the meeting card shows decides which caption it is:
     a place or a time already agreed means moving, nothing means setting. */
  const meetingLabels: Record<string, string> = {}
  /* T_UX.29 pt.2 п.2 (owner, 2026-09-20): «Всё ещё предлагается выбрать способ
     передачи, хотя он уже назначен — и написано, что условия уже согласованы.»

     The caption was decided by the place and the time alone, so an **accepted**
     «Вручение перенесено» that named only the method left the screen offering
     «Способ передачи» over a method the two of them had already agreed — while
     the boarding pass above said «Условия согласованы». An answered card is an
     arrangement whatever fields it carried; the missing time is what
     `MeetingNote` says on its own line, not a reason to call the whole section
     unset. */
  const meetingStands: Record<'handover' | 'delivery', boolean> = {
    handover: false,
    delivery: false,
  }
  for (const [kind, stageOfMeeting] of [
    ['pickup.proposed', 'handover'],
    ['dropoff.proposed', 'delivery'],
  ] as const) {
    const arranged = meetingOf(terms, messages, stageOfMeeting)
    const answered = messages.some(
      (m) => m.card_kind === kind && m.card_state === 'accepted',
    )
    meetingStands[stageOfMeeting] = Boolean(
      arranged.place || arranged.at || answered,
    )
    if (!meetingStands[stageOfMeeting]) {
      meetingLabels[kind] = t(
        `cards.kind.${stageOfMeeting === 'handover' ? 'pickup' : 'dropoff'}_assign`,
      )
    }
  }

  /* T_UX.29 pt.2 п.4 (owner, 2026-09-20): «После того как выбрано время
     вручения при способе передачи "Лично в руки", окно должно называться не
     "Передано в доставку", а "Вручено".»

     One card, two acts: `delivery.declared` ends the carriage either by putting
     the parcel into somebody's hands or by handing it to a service that will.
     «Передано в доставку» over a meeting at a café describes the wrong event to
     the two people standing at it — and an arbiter reads these labels. The
     agreed method is what decides, so the caption follows it. */
  if (meetingOf(terms, messages, 'delivery').method === 'in_person') {
    meetingLabels['delivery.declared'] = t('cards.kind.delivery_handed')
  }

  /* T_UX.29 п.4 (owner, 2026-09-20): «Раздел "Способ передачи"… должен быть
     доступен для настройки только Перевозчику, Получатель либо соглашается,
     либо предлагает изменения.»

     Has anything been said about the delivery yet — the mirror of the server's
     `_delivery_already_named`, read the same way. An unanswered
     `dropoff.proposed` counts: a proposal is a conversation opened, and the
     answer to one the recipient disagrees with is a counter-proposal rather
     than a refusal and silence. The method alone does not count — every
     agreement carries one, so counting it would mean the delivery was always
     already named and the rule below would never fire once. */
  const deliveryNamed =
    Boolean(terms?.payload?.delivery_place || terms?.payload?.delivery_at) ||
    messages.some((m) => m.card_kind === 'dropoff.proposed')

  /* T_UX.29 п.1 — the pending rule has one exception, and it is the card the
     stage is named after. A `transit.update` waits on the other side's
     «Принято», and the journey does not: a carrier who declared a delay still
     has to declare the landing an hour later. Standing on its own pending card
     is exactly how «Статус в пути» vanished from the stage called «В пути».
     Every other kind keeps the rule — a second unanswered «Передал
     перевозчику» is two contradictory declarations of one act.

     T_UX.29 п.4 — and nothing is named before the carrier names it. The first
     word on «как вручаем» is theirs, because they are the one who will be
     standing there holding the parcel; afterwards everybody who may raise the
     card gets it back. The server refuses the same way — this is what keeps the
     screen from offering a press that ends in a refusal. */
  const mineNow = myRole
    ? stageKinds.filter(
        (kind) =>
          (!pendingKinds.has(kind) || kind === 'transit.update') &&
          (kind !== 'dropoff.proposed' ||
            myRole === 'carrier' ||
            deliveryNamed) &&
          formsForRole(myRole).some((form) => form.kind === kind),
      )
    : []

  /* T_UX.29 pt.2 п.2 — and an arrangement that already stands is not the form
     this stage opens with. `CardActions` expands the first action it is given
     (`T_UX.28 п.3`), so «Способ передачи» unfolded itself over a meeting the
     two of them had agreed, with every field blank. Moved to the end it is
     still one press away — which is what changing an arrangement should cost —
     and the step that is actually next opens instead.

     Stable sort: everything else keeps the protocol order the stage declared. */
  const stillToArrange = (kind: string) =>
    (kind === 'dropoff.proposed' && meetingStands.delivery) ||
    (kind === 'pickup.proposed' && meetingStands.handover)
      ? 1
      : 0
  const ordered = [...mineNow].sort(
    (a, b) => stillToArrange(a) - stillToArrange(b),
  )

  return (
    <div className="space-y-4">
      {/* The ladder. Done, now, ahead — the «список смены статусов», read off
          the status rather than kept as a second record beside it.

          T_UX.29 п.6 (owner, 2026-09-20): «Панель прогресса должна быть
          горизонтальной и в одну строку, и статусы выделяться чуть более
          явно.»

          Seven rungs stacked vertically cost the top third of the panel to say
          one thing — where the deal stands — and pushed the stage's own actions
          below the fold on a laptop. Horizontal, it is a strip above them: the
          whole route at a glance, and the eye lands on the actions first.

          The three states are told apart by shape now, not only by opacity. The
          live rung is a filled chip and the rest is plain text, so «где мы
          сейчас» survives a glance, a dim screen and a colour-blind reader —
          three ways the old 50 %/30 % difference failed.

          Scrolls rather than wraps on a narrow screen: «в одну строку» is the
          instruction, and a route broken across two lines reads as two
          routes. */}
      <ol className="flex items-center overflow-x-auto pb-0.5 -mx-1 px-1">
        {DEAL_STAGES.map((stage, index) => {
          const done = index < currentIndex
          const live = index === currentIndex
          return (
            <li
              key={stage.key}
              aria-current={live ? 'step' : undefined}
              className="flex items-center shrink-0"
            >
              {index > 0 && (
                <span
                  aria-hidden
                  className={`w-3 sm:w-4 h-px shrink-0 ${
                    done || live ? 'bg-navy/30' : 'bg-navy/10'
                  }`}
                />
              )}
              <span
                className={
                  live
                    ? 'px-2.5 py-1 rounded-full bg-cyan/15 border border-cyan/60 font-display font-semibold text-xs text-navy whitespace-nowrap'
                    : `px-1 font-body text-[11px] whitespace-nowrap ${
                        done ? 'text-navy/55' : 'text-navy/25'
                      }`
                }
              >
                {t(`stages.${stage.key}`)}
                {done && <span className="ml-0.5 text-navy/30">✓</span>}
              </span>
            </li>
          )
        })}
      </ol>

      <div className="border-t border-navy/10 pt-4 space-y-3">
        {/* A cancelled deal stands on the last rung without having walked it, so
            the heading says so: «Завершено» over a delivery that never happened
            is the record telling the two people the opposite of what they
            agreed. */}
        <div>
          <h2 className="font-display font-semibold text-base text-navy">
            {t(status === 'cancelled' ? 'stages.cancelled' : `stages.${currentKey}`)}
          </h2>
          <p className="text-xs font-body text-navy/50 mt-0.5">
            {t(
              status === 'cancelled'
                ? 'stages.hint.cancelled'
                : `stages.hint.${currentKey}`,
            )}
          </p>
          {/* T_UX.29 pt.2 пп.1, 3 — where it is now, for everybody and not
              only for the carrier who typed it. Drawn above «Дальше», because
              «сейчас» is what the next line is measured from, and silent when
              the last word about the journey is the rung itself: «Сейчас:
              Прилетел» under a heading that says «Прилетел» is a line that
              repeats rather than informs. */}
          {transitNow && (
            <p className="text-xs font-body text-navy mt-1">
              <span className="font-medium">
                {t('stages.now', {
                  status: t(`cards.opt.${transitNow}`, transitNow),
                })}
              </span>
              {/* The sentence is what makes the line worth reading; without one
                  a dangling dash is all that is added. */}
              {transitHint && ` — ${transitHint}`}
            </p>
          )}
          {/* T_UX.28 п.7 — what is planned next, in one line, under the stage
              it follows. */}
          {nextStep && (
            <p className="text-xs font-body text-navy/70 mt-1">{nextStep}</p>
          )}
        </div>

        {/* Stage one is the terms, and the terms are a form rather than a chip:
            the price is the one answer on this screen that costs money. */}
        {currentKey === 'terms' && myRole && (
          <div>
            {termsOpen ? (
              /* Prefilled with the version being edited: the API takes the whole
                 card, so somebody moving a meeting place would otherwise retype
                 the price to keep it — and a retyped number is where a deal
                 quietly changes value. */
              <TermsProposeForm
                dealId={dealId}
                current={terms?.payload ?? null}
                fromBoard={deal}
                supersedesId={
                  terms && terms.card_state === 'pending' ? terms.id : null
                }
                myRole={myRole}
                onDone={() => {
                  setTermsOpen(false)
                  onDone()
                }}
              />
            ) : (
              <button
                type="button"
                onClick={() => setTermsOpen(true)}
                className="bg-navy text-ivory font-display font-medium text-sm px-4 py-2 min-h-[2.75rem] rounded-field hover:bg-navy-mid transition-colors"
              >
                {terms ? t('deals.editTerms') : t('deals.proposeTerms')}
              </button>
            )}
          </div>
        )}

        {/* T3.11.27 — «После того как договорились об условиях, должно
            появляться описание где вы встречаетесь и восколько» (owner,
            2026-09-12). Drawn above the buttons, because it is what the buttons
            are about; at the far end it describes the delivery instead, which
            is the same arrangement read from the other side of the flight. */}
        {/* T_DEAL.1 — «ожидание, иногда платное» (owner, 2026-09-20). Above
            the meeting, because while the parcel is in storage the question
            «когда встречаемся» has a price attached to its answer. Drawn only
            when the deal is actually in one; the server decides that. */}
        {deal?.storage && <StorageNote storage={deal.storage} />}

        {/* T_UX.29 pt.3 — the checklist for the act the button below declares:
            what to look at, what the sum is, and what to attach when the money
            moves by transfer. Drawn only for the person who can press it — a
            memo about somebody else's afternoon is one more thing to read. */}
        {myRole && mineNow.includes('delivery.declared') && (
          <HandoverNote
            terms={terms}
            side={myRole === 'carrier' ? 'giving' : 'taking'}
            money={
              myRole === 'carrier' ? 'receive' : myRole === payer ? 'pay' : null
            }
          />
        )}

        {(currentKey === 'handover' ||
          currentKey === 'arrived' ||
          currentKey === 'delivery') && (
          <MeetingNote
            terms={terms}
            messages={messages}
            stage={currentKey === 'handover' ? 'handover' : 'delivery'}
            myRole={myRole}
          />
        )}

        {/* T3.11.27 — «Передал перевозчику (где)» (owner, walking the flow
            2026-09-12). The answer was «nowhere, for you»: `handoff.declared`
            is the sender's card, so a carrier at that stage saw an empty panel
            and went looking for a button that is not theirs to press.

            A blank is not an answer. Naming whose turn it is costs one line and
            replaces the hunt — and it is true of every stage, not only this
            one: a deal is two people acting in turn, and the half of the time
            it is not your turn is exactly when the screen used to say nothing.

            Drawn only when the stage *has* actions and none of them are this
            role's: at a stage nobody acts on (`closed`, `delivery`) silence is
            correct, and «ждём вторую сторону» there would be a lie. */}
        {myRole &&
          !TERMINAL_STATUSES.includes(status) &&
          liveKinds.length > 0 &&
          mineNow.length === 0 && (
            <p className="text-xs font-body text-navy/45">
              {t('stages.theirTurn')}
            </p>
          )}

        {mineNow.length > 0 && (
          <CardActions
            dealId={dealId}
            myRole={myRole}
            only={ordered}
            labels={meetingLabels}
            doneStages={doneStages}
            /* T_UX.29 п.1 — «Статус "В пути" это то же самое что и этап "В
               пути"». On the two rungs that are the flight, the status form is
               the stage, so it is drawn open rather than offered. */
            pinned="transit.update"
            /* T_UX.29 pt.3 — «И кнопка — "Завершить передачу"» (owner,
               2026-09-20). The window keeps the name of the act («Вручено»),
               the button says what pressing it does. */
            submitLabels={{ 'delivery.declared': t('handover.finish') }}
            onDone={onDone}
          />
        )}

        {/* T3.11.27 — the one-press close is gone (owner, 2026-09-12).
            `POST /confirm` let the sender end a deal without «Сколько денег
            получено» and without anybody confirming receipt, and that is
            exactly how it ended: «сделка закрылась», with the two buttons that
            should have closed it nowhere to be seen, because the stage they
            live on had already passed.

            It was added for the postal stretch on the honest argument that the
            carrier has done their part and should not wait on a post office.
            That argument survives — but it is answered by the settlement pair,
            not by skipping it: the sender raises «Оплата произведена» while the
            parcel is still travelling, the carrier confirms, and the deal
            closes on two people saying so. One button closing a deal past the
            money was the same second route to a status that was taken off the
            boarding pass for the same reason. */}

        {/* T3.11.27 — the stage's own camera button is gone (owner,
            2026-09-12). Every photograph in a deal now hangs on the act it is
            evidence for: the custody photos travel with their cards, and «вот
            что я отправляю» travels with the proposal, where it can be several.
            A picture filed beside an act instead of on it is what made a card
            unconfirmable with its own evidence three lines above it. */}

        {/* T3.11.27 — «Отдано, но не оплачено — доступно "Пригласить арбитра"».
            Stated as a sentence with the action under it: the person reading it
            is holding an unpaid delivery and needs to be told this is a normal
            thing to do, not to hunt for a button.

            A deal already in dispute cannot be here: `handedOverUnpaid` is
            `posted` or `delivered`, and `disputed` is neither. */}
        {handedOverUnpaid && (
          <div className="pt-2 border-t border-navy/5 space-y-1">
            <p className="text-xs font-body text-navy/50">
              {t('stages.unpaidHint')}
            </p>
            <button
              type="button"
              onClick={() => setDisputeOpen(true)}
              className="border border-danger/30 text-danger font-body font-medium text-sm px-4 py-2 min-h-[2.75rem] rounded-field hover:bg-danger/5 transition-colors"
            >
              {t('dispute.openButton')}
            </button>
          </div>
        )}

        {/* Never gated by stage, never in the way: a problem, a cancellation and
            the arbiter are needed exactly when the ladder has stopped describing
            what is happening. */}
        {myRole && !TERMINAL_STATUSES.includes(status) && (
          <div className="pt-2 border-t border-navy/5">
            {moreOpen ? (
              <div className="space-y-2">
                <CardActions
                  dealId={dealId}
                  myRole={myRole}
                  only={ALWAYS_AVAILABLE}
                  muted
                  onDone={onDone}
                />
                {/* Reachable at any point, quiet until it is needed. Hidden
                    above once the parcel has been handed over, where it is
                    already stated at full weight. */}
                {canDispute && !handedOverUnpaid && (
                  <button
                    type="button"
                    onClick={() => setDisputeOpen(true)}
                    className="text-xs font-body text-danger/70 hover:text-danger"
                  >
                    {t('dispute.openButton')}
                  </button>
                )}
                {/* T3.12.05 — the recipient's way to the arbiter is through the
                    sender: a request the sender reads, not a dispute. */}
                {asking &&
                  ['accepted', 'in_transit', 'posted', 'delivered'].includes(status) && (
                    <button
                      type="button"
                      onClick={() => setDisputeOpen(true)}
                      className="text-xs font-body text-danger/70 hover:text-danger"
                    >
                      {t('disputeRequest.button')}
                    </button>
                  )}
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setMoreOpen(true)}
                className="text-xs font-body text-navy/40 hover:text-navy"
              >
                {t('stages.more')}
              </button>
            )}
          </div>
        )}
      </div>

      {/* T3.11.27 — one action with a reason from a list (owner, 2026-09-07):
          «не заплатили · не довезли · повреждено · другое». Four categories an
          arbiter can sort a queue by; the sentence goes underneath, where it
          explains the category rather than replacing it. */}
      {disputeOpen && (
        <div
          className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-modal flex items-center justify-center p-4"
          onClick={() => setDisputeOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-card p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <h2 className="font-display font-semibold text-lg text-navy">
              {asking ? t('disputeRequest.title') : t('dispute.modalTitle')}
            </h2>
            <p className="text-sm font-body text-navy/60">
              {asking ? t('disputeRequest.hint') : t('dispute.modalHint')}
            </p>
            <select
              value={disputeReason}
              onChange={(e) => setDisputeReason(e.target.value as DisputeReason)}
              className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            >
              {DISPUTE_REASONS.map((r) => (
                <option key={r} value={r}>
                  {t(`dispute.reason.${r}`)}
                </option>
              ))}
            </select>
            <textarea
              value={disputeDetails}
              onChange={(e) => setDisputeDetails(e.target.value)}
              rows={3}
              placeholder={t('dispute.reasonPlaceholder') as string}
              className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            />
            {disputeError && (
              <p className="text-xs font-mono text-danger">{disputeError}</p>
            )}
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setDisputeOpen(false)}
                className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={raiseDispute}
                disabled={disputeBusy}
                className="bg-danger text-white font-display font-medium px-4 py-2 rounded-field text-sm hover:bg-danger/90 transition-colors disabled:opacity-40"
              >
                {disputeBusy ? '…' : asking ? t('disputeRequest.submit') : t('dispute.submit')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
