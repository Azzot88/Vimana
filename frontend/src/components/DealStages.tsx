import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { DealDetail, DealStatus } from '../api/deals'
import { DISPUTE_REASONS, openDispute, type DisputeReason } from '../api/admin'
import { sendPhotoMessage, type VaultMessage } from '../api/dealvault'
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
  onMessage: (msg: VaultMessage) => void
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
 *  The photograph belongs to the stage: at a handover it is a picture of the
 *  handover, before posting it is the open parcel. So the kind is preselected
 *  rather than chosen from a dropdown — that dropdown asked, at the moment
 *  somebody is holding a parcel and a phone, a question with one answer.
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
  onMessage,
}: Props) {
  const { t } = useTranslation()
  const [termsOpen, setTermsOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
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
  const [disputeError, setDisputeError] = useState('')

  const currentKey: DealStageKey = stageOf(status)
  const current = DEAL_STAGES.find((s) => s.key === currentKey)
  const currentIndex = stageIndex(currentKey)

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !current?.photo) return
    setBusy(true)
    setError('')
    try {
      onMessage(await sendPhotoMessage(dealId, file, current.photo))
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : t('chat.uploadFailed'))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const raiseDispute = async () => {
    setDisputeBusy(true)
    setDisputeError('')
    try {
      await openDispute(dealId, disputeReason, disputeDetails.trim() || undefined)
      setDisputeOpen(false)
      setDisputeDetails('')
      onDone()
    } catch {
      setDisputeError(t('dispute.openError'))
    } finally {
      setDisputeBusy(false)
    }
  }

  const canAttach =
    current?.photo && myRole && (current.photoBy ?? []).includes(myRole)

  /* T3.11.27 — «Отдано, но не оплачено» (owner, 2026-09-07). The parcel is with
     the person it was for and the money has not been settled: the one moment
     the arbiter stops being a last resort and becomes the next step. Named on
     the panel rather than left to be found, because somebody in this position
     is already unsure whether they are allowed to complain. */
  const handedOverUnpaid =
    (status === 'delivered' || status === 'posted') && Boolean(myRole)

  const canDispute =
    Boolean(myRole) &&
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
  const liveKinds = Array.from(
    new Set(
      DEAL_STAGES.filter(
        (s) => s.key === currentKey || s.statuses.includes(status),
      ).flatMap((s) => s.kinds),
    ),
  )
  const stageKinds = liveKinds.filter(
    (kind) => kind !== 'payment.declared' || myRole === payer,
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
  const mineNow = myRole
    ? stageKinds.filter(
        (kind) =>
          !pendingKinds.has(kind) &&
          formsForRole(myRole).some((form) => form.kind === kind),
      )
    : []

  return (
    <div className="space-y-4">
      {/* The ladder. Done, now, ahead — the «список смены статусов», read off
          the status rather than kept as a second record beside it. */}
      <ol className="space-y-1">
        {DEAL_STAGES.map((stage, index) => {
          const done = index < currentIndex
          const live = index === currentIndex
          return (
            <li
              key={stage.key}
              className={`flex items-center gap-2 text-sm font-body ${
                live
                  ? 'text-navy font-medium'
                  : done
                    ? 'text-navy/50'
                    : 'text-navy/30'
              }`}
            >
              <span
                aria-hidden
                className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                  live ? 'bg-cyan' : done ? 'bg-navy/40' : 'bg-navy/15'
                }`}
              />
              {t(`stages.${stage.key}`)}
              {done && <span className="text-xs text-navy/30">✓</span>}
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
            only={mineNow}
            onDone={onDone}
          />
        )}

        {/* T3.11.27 — the one-press close is gone (owner, 2026-09-12).
            `POST /confirm` let the sender end a deal without «Сколько денег
            получено» and without anybody confirming receipt, and that is
            exactly how it ended: «сделка закрылась», with the two buttons that
            should have closed it nowhere to be seen, because the stage they
            live on had already passed.

            It was added for the postal leg on the honest argument that the
            carrier has done their part and should not wait on a post office.
            That argument survives — but it is answered by the settlement pair,
            not by skipping it: the sender raises «Оплата произведена» while the
            parcel is still travelling, the carrier confirms, and the deal
            closes on two people saying so. One button closing a deal past the
            money was the same second route to a status that was taken off the
            boarding pass for the same reason. */}

        {canAttach && (
          <label className="inline-flex items-center gap-2 cursor-pointer text-sm font-body text-cyan hover:underline">
            📷 {busy ? t('common.sending') : t(`stages.photo.${currentKey}`)}
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
              onChange={upload}
              className="hidden"
              disabled={busy}
            />
          </label>
        )}

        {error && <p className="text-xs font-body text-amber">{error}</p>}

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
              {t('dispute.modalTitle')}
            </h2>
            <p className="text-sm font-body text-navy/60">
              {t('dispute.modalHint')}
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
                {disputeBusy ? '…' : t('dispute.submit')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
