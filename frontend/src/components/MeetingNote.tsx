import { useTranslation } from 'react-i18next'
import type { VaultMessage } from '../api/dealvault'
import type { Terms } from '../api/terms'
import type { DealRole } from '../lib/cardForms'
import { usePrefs } from '../hooks/usePrefs'

/**
 * T3.11.27 — where you are meeting, at what time, and what to do there.
 *
 * Owner, 2026-09-12: «После того как договорились об условиях, должно появляться
 * описание где вы встречаетесь и восколько… Также должна быть инфа что надо
 * проверить вес и сравнить содержимое с описанием. Это памятка для перевозчика.
 * То есть для обоих должно быть описание места встречи. Указатель сколько часов
 * до неё осталось.»
 *
 * Both halves of that are on this card and neither is new information — the
 * place and the time are in the agreement, the checks are in the protocol. What
 * was missing is that they were nowhere near the moment they matter: the place
 * sat folded inside the agreement card, and «взвесьте и сверьте с описанием»
 * existed only as the consequence of a dispute nobody had read the rules for.
 *
 * **The clock is the point.** A date somebody agreed to three days ago is read
 * as an arrangement; «через 2 часа» is read as a thing to leave for now. That is
 * the whole difference between a card that informs and one that is acted on.
 *
 * The checklist is the carrier's alone. The sender does not weigh their own
 * parcel at the handover and does not compare it with their own description —
 * giving them the same lines would make the card a wall of advice, and a wall of
 * advice is read by nobody.
 *
 * Functions (PROJECT §6.2a):
 * - `MeetingNote({ terms, messages, stage, myRole })` — default export.
 *   Called by: `components/DealStages`.
 */
interface Props {
  terms: Terms | null
  messages: VaultMessage[]
  /** Which end of the route: the handover at the start, the delivery at the end. */
  stage: 'handover' | 'delivery'
  myRole: DealRole | null
  /** Fixed «now», for tests. */
  now?: number
}

const CARD_OF = {
  handover: 'pickup.proposed',
  delivery: 'dropoff.proposed',
} as const

interface Meeting {
  method?: string
  place?: string
  at?: string
  /** T_UX.28 п.9 — this arrangement is somebody's proposal, not an agreement:
   *  the card is still awaiting an answer. Drawn differently, because «где вы
   *  встречаетесь» and «где вам предлагают встретиться» are different facts and
   *  only one of them is safe to plan around. */
  proposed?: boolean
}

/** The arrangement as it stands: the last **accepted** meeting card wins, and
 *  the agreement is what speaks when no card has moved it.
 *
 *  Accepted only, deliberately. A proposal awaiting an answer is somebody's
 *  request, not an arrangement — printing it as «где вы встречаетесь» would tell
 *  two people they had agreed on something one of them has not read yet. */
export function meetingOf(
  terms: Terms | null,
  messages: VaultMessage[],
  stage: 'handover' | 'delivery',
): Meeting {
  const kind = CARD_OF[stage]
  const card = [...messages]
    .reverse()
    .find((m) => m.card_kind === kind && m.card_state === 'accepted')
  if (card) {
    const p = (card.card_payload ?? {}) as Record<string, unknown>
    return {
      method: typeof p.method === 'string' ? p.method : undefined,
      place: typeof p.city === 'string' ? p.city : undefined,
      at: typeof p.at === 'string' ? p.at : undefined,
    }
  }
  const p = terms?.payload
  if (!p) return {}
  /* Spelled out rather than indexed by `${stage}_place`: the payload is a named
     shape, and a computed key would compile only by widening it to a bag of
     unknowns — which is how a renamed field starts rendering as blank instead
     of failing to build. */
  return stage === 'handover'
    ? {
        method: p.handover_method ?? undefined,
        place: p.handover_place ?? undefined,
        at: p.handover_at ?? undefined,
      }
    : {
        method: p.delivery_method ?? undefined,
        place: p.delivery_place ?? undefined,
        at: p.delivery_at ?? undefined,
      }
}

/** The standing request: the last meeting card nobody has answered yet.
 *
 *  T_UX.28 п.9 — it used to be invisible until answered, so the screen said
 *  «время не назначено» while a card two lines below named a time, and the
 *  person who had proposed it saw no trace of their own request. It is read
 *  apart from `meetingOf` on purpose: the arrangement is what the rest of the
 *  screen plans around, and a request is not an arrangement. */
function proposedMeeting(
  messages: VaultMessage[],
  stage: 'handover' | 'delivery',
): Meeting {
  const kind = CARD_OF[stage]
  const card = [...messages]
    .reverse()
    .find((m) => m.card_kind === kind && m.card_state === 'pending')
  if (!card) return {}
  const p = (card.card_payload ?? {}) as Record<string, unknown>
  return {
    method: typeof p.method === 'string' ? p.method : undefined,
    place: typeof p.city === 'string' ? p.city : undefined,
    at: typeof p.at === 'string' ? p.at : undefined,
    proposed: true,
  }
}

export default function MeetingNote({
  terms,
  messages,
  stage,
  myRole,
  now = Date.now(),
}: Props) {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const arranged = meetingOf(terms, messages, stage)
  /* An unanswered request speaks only where nothing has been arranged at all.
     Where something has, that something is what the two of them are going by,
     and overwriting it with one side's request would tell both of them they
     had agreed on something one of them has not read. */
  const meeting =
    arranged.place || arranged.at || arranged.method
      ? arranged
      : proposedMeeting(messages, stage)

  // Nothing agreed and nothing proposed: there is no arrangement to describe,
  // and a card saying «место не назначено» over an empty line would be one more
  // thing to read that says nothing.
  if (!meeting.place && !meeting.at && !meeting.method) return null

  const left = meeting.at ? new Date(meeting.at).getTime() - now : null
  const hours = left === null ? null : Math.floor(left / 3_600_000)
  const minutes = left === null ? null : Math.round(left / 60_000)

  const countdown = () => {
    if (left === null) return null
    if (left < 0) return t('meeting.passed')
    if (hours! < 1) return t('meeting.minutes', { count: Math.max(minutes!, 1) })
    return t('meeting.hours', { count: hours! })
  }

  const urgent = left !== null && left >= 0 && left < 3 * 3_600_000

  return (
    <div className="rounded-2xl border border-cyan/30 bg-cyan/5 p-4 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <h3 className="text-sm font-display font-semibold text-navy">
          {t(`meeting.title.${stage}`)}
        </h3>
        {/* T_UX.28 п.9 — said out loud, because everything below it reads like
            an arrangement and this one is still a question. */}
        {meeting.proposed && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono uppercase bg-amber/20 text-navy border border-amber/40">
            {t('meeting.proposed')}
          </span>
        )}
      </div>

      {(meeting.place || meeting.method) && (
        <p className="text-sm font-body text-navy/80">
          {meeting.place}
          {meeting.place && meeting.method ? ' · ' : ''}
          {meeting.method ? t(`cards.opt.${meeting.method}`, meeting.method) : ''}
        </p>
      )}

      <p className="text-sm font-body text-navy/70">
        {meeting.at ? prefs.dateTime(meeting.at) : t('meeting.noTime')}
        {countdown() && (
          <span
            className={`ml-2 text-xs font-mono px-2 py-0.5 rounded-full ${
              urgent
                ? 'bg-amber/20 text-navy border border-amber/50'
                : 'bg-white text-navy/60 border border-navy/10'
            }`}
          >
            {countdown()}
          </span>
        )}
      </p>

      {/* The carrier's memo. Two lines, because two things go wrong at a
          handover and both are settled by looking: a parcel heavier than the
          agreement says costs the carrier their own allowance, and contents that
          do not match the description are what an arbiter is later asked about
          with no way to answer. */}
      {myRole === 'carrier' && stage === 'handover' && (
        <ul className="pt-1 space-y-1 border-t border-cyan/20">
          <li className="text-xs font-body text-navy/70">{t('meeting.memo.weigh')}</li>
          <li className="text-xs font-body text-navy/70">
            {t('meeting.memo.compare')}
          </li>
          <li className="text-xs font-body text-navy/70">{t('meeting.memo.photo')}</li>
        </ul>
      )}
    </div>
  )
}
