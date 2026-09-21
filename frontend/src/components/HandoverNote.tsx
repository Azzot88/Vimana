import { useTranslation } from 'react-i18next'
import type { Terms } from '../api/terms'
import MonoText from './MonoText'

/**
 * T_UX.29 pt.3 — what to do at the door, said before the button that ends it.
 *
 * Owner, 2026-09-20: «У получателя нет окна подтверждения правильности груза и
 * деталей для проверки. Надо указать: примите груз, проверьте упаковку,
 * содержимое. Сумма к оплате такая-то, проверьте. Отправьте деньги или
 * передайте в руки… Если все совпадает — завершите передачу.» And the same for
 * the side handing it over: «передайте отправление, дайте получателю всё
 * проверить… получите деньги или дождитесь перевода, сделайте скрин и
 * разместите в чате».
 *
 * **Both halves of one act, and that is why they are one component.** The
 * handover in hand is «груз и деньги одним движением» (`D-CARGO-MODEL` (5)):
 * two people doing opposite things at the same minute, and a memo written for
 * only one of them leaves the other guessing what the first is checking.
 *
 * The sum is printed for the payer alone, and printed rather than described:
 * «сумма к оплате такая-то, проверьте» is an instruction to compare, and there
 * is nothing to compare against if the screen does not say the number. Whose
 * money it is comes from the agreement (`payer`), not from a role — a deal can
 * be «получатель платит на месте».
 *
 * Not a card and not a state: nothing here is recorded, it is the checklist for
 * the act the card below declares. The same reasoning as `MeetingNote`'s memo,
 * one step later on the ladder.
 *
 * Functions (PROJECT §6.2a):
 * - `HandoverNote({ terms, side, paying })` — default export.
 *   Called by: `components/DealStages`.
 */
interface Props {
  terms: Terms | null
  /** Which end of the act this reader is standing at. */
  side: 'giving' | 'taking'
  /** This reader's side of the money: they owe it, they are owed it, or the
   *  settlement is somebody else's (a recipient in a deal the sender pays). */
  money: 'pay' | 'receive' | null
}

export default function HandoverNote({ terms, side, money }: Props) {
  const { t } = useTranslation()
  const price = terms?.payload?.price_total
  const currency = terms?.payload?.currency ?? 'USD'
  const method = terms?.payload?.payment_method

  return (
    <div className="rounded-2xl border border-amber/40 bg-amber/5 p-4 space-y-2">
      <h3 className="text-sm font-display font-semibold text-navy">
        {t(`handover.title.${side}`)}
      </h3>

      {/* The money lines belong to whoever the agreement says settles. A
          recipient in a deal the sender pays from afar checks the parcel and
          nothing else, and «передайте деньги» there would be an instruction to
          do somebody else's job at the door. */}
      <ul className="space-y-1">
        {(side === 'giving'
          ? ['hand', 'letThemCheck', 'takeMoney', 'screenshot']
          : money === 'pay'
            ? ['check', 'contents', 'pay', 'screenshot']
            : ['check', 'contents']
        ).map((line) => (
          <li key={line} className="text-xs font-body text-navy/75">
            {t(`handover.${side}.${line}`)}
          </li>
        ))}
      </ul>

      {/* The number, for whoever owes it and for whoever is counting it. Stated
          as data rather than folded into a sentence: this is the one line on
          the card somebody compares with what is in their hand. */}
      {typeof price === 'number' && money && (
        <div className="flex justify-between gap-4 pt-2 border-t border-amber/30">
          <span className="text-xs font-body text-navy/60">
            {t(money === 'pay' ? 'handover.toPay' : 'handover.toReceive')}
          </span>
          <MonoText className="text-sm text-navy">
            {price} {currency}
            {method ? ` · ${t(`cards.opt.${method}`, method)}` : ''}
          </MonoText>
        </div>
      )}

      <p className="text-xs font-body text-navy/75 pt-1">
        {t(`handover.${side}.finish`)}
      </p>
    </div>
  )
}
