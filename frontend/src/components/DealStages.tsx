import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { confirmDeal, type DealStatus } from '../api/deals'
import { sendPhotoMessage, type VaultMessage } from '../api/dealvault'
import {
  ALWAYS_AVAILABLE,
  DEAL_STAGES,
  stageIndex,
  stageOf,
  type DealStageKey,
} from '../lib/dealStages'
import type { Terms } from '../api/terms'
import type { DealRole } from '../lib/cardForms'
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
 *  Functions (PROJECT §6.2a):
 *  - `DealStages({...})` — default export. Called by: `pages/DealVaultPage`.
 */
export default function DealStages({
  dealId,
  status,
  myRole,
  terms,
  onDone,
  onMessage,
}: Props) {
  const { t } = useTranslation()
  const [termsOpen, setTermsOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

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

  const confirm = async () => {
    setBusy(true)
    setError('')
    try {
      await confirmDeal(dealId)
      onDone()
    } catch {
      setError(t('deals.actionFailed'))
    } finally {
      setBusy(false)
    }
  }

  const canAttach =
    current?.photo && myRole && (current.photoBy ?? []).includes(myRole)

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
        <div>
          <h2 className="font-display font-semibold text-base text-navy">
            {t(`stages.${currentKey}`)}
          </h2>
          <p className="text-xs font-body text-navy/50 mt-0.5">
            {t(`stages.hint.${currentKey}`)}
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

        {current && current.kinds.length > 0 && (
          <CardActions
            dealId={dealId}
            myRole={myRole}
            only={current.kinds}
            onDone={onDone}
          />
        )}

        {/* T3.11.17 — «Подтвердить получение» lives at the delivery stage now,
            not on the boarding pass. The owner's answer 2026-09-07: after
            «Отправлено по почте» the sender may close straight away — the
            carrier has done everything that depends on them, and holding the
            deal open for somebody else's postal schedule punishes them for the
            post office's pace. */}
        {currentKey === 'delivery' && myRole === 'sender' && (
          <div className="space-y-1">
            <button
              type="button"
              onClick={confirm}
              disabled={busy}
              className="bg-success text-white font-display font-medium text-sm px-4 py-2 min-h-[2.75rem] rounded-field hover:opacity-90 disabled:opacity-50"
            >
              {t('deals.confirmReceipt')}
            </button>
            {status === 'posted' && (
              <p className="text-xs font-body text-navy/45">
                {t('stages.stillTravelling')}
              </p>
            )}
          </div>
        )}

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

        {/* Never gated by stage, never in the way: a problem and a cancellation
            are needed exactly when the ladder has stopped describing what is
            happening. */}
        {myRole && (
          <div className="pt-2 border-t border-navy/5">
            {moreOpen ? (
              <CardActions
                dealId={dealId}
                myRole={myRole}
                only={ALWAYS_AVAILABLE}
                muted
                onDone={onDone}
              />
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
    </div>
  )
}
