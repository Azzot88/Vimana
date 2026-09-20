import { useTranslation } from 'react-i18next'
import type { DealDetail } from '../api/deals'
import { usePrefs } from '../hooks/usePrefs'
import MonoText from './MonoText'

/**
 * T_DEAL.1 — посылка лежит и ждёт, и это иногда стоит денег.
 *
 * Owner, 2026-09-20: «Иногда бывают ситуации, когда посылка прилетела и не может
 * быть вручена, или ожидает стыковочного рейса… Состояние этапа — ни расчёта,
 * ни получения. Ожидание, иногда платное. Должен быть счётчик времени. И
 * указание на то, сколько длится бесплатное хранение и когда начинается платное
 * и сколько оно стоит. Это должно быть в статусе.»
 *
 * So this card answers three questions and no others: **до когда бесплатно**,
 * **сколько уже набежало**, **сколько назвал перевозчик**. The third is separate
 * from the second on purpose — the счётчик is advisory (the same decision), and
 * a screen that showed one number would be claiming the carrier had charged it.
 *
 * Nothing is computed here. The server owns the boundary rule (a storage day
 * begins at six in the morning, local to the parcel) and the ceiling; a second
 * arithmetic on the client would be a second answer to «сколько я должен».
 *
 * Functions (PROJECT §6.2a):
 * - `StorageNote({ storage })` — default export.
 *   Called by: `components/DealStages`.
 */
interface Props {
  storage: NonNullable<DealDetail['storage']>
}

export default function StorageNote({ storage }: Props) {
  const { t } = useTranslation()
  const prefs = usePrefs()

  const free = storage.paid_days === 0 && !storage.capped
  const charged = storage.charged

  return (
    <div className="rounded-2xl border border-amber/40 bg-amber/5 p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-display font-semibold text-navy">
          {t('storage.title')}
        </h3>
        <MonoText className="text-[10px] uppercase tracking-widest text-navy/40">
          {t(free ? 'storage.stateFree' : 'storage.statePaid')}
        </MonoText>
      </div>

      <p className="text-sm font-body text-navy/70">
        {free
          ? t('storage.freeUntil', { when: prefs.dateTime(storage.free_until) })
          : t('storage.freeOver', { when: prefs.dateTime(storage.free_until) })}
      </p>

      {!free && (
        <div className="space-y-1">
          <div className="flex justify-between gap-4">
            <span className="text-xs font-body text-navy/50">
              {t('storage.paidDays')}
            </span>
            <MonoText className="text-xs text-navy">{storage.paid_days}</MonoText>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-xs font-body text-navy/50">
              {t('storage.accrued')}
            </span>
            <MonoText className="text-xs text-navy">
              {/* T_DEAL.1 — `null` is «вес никто не назвал», not «бесплатно».
                  Showing a nought here would quietly waive the carrier's fee. */}
              {storage.amount === null
                ? t('storage.unknownSum')
                : `${storage.amount} ${storage.currency}`}
            </MonoText>
          </div>
        </div>
      )}

      <p className="text-xs font-body text-navy/50">
        {t('storage.tariff', {
          price: storage.price,
          currency: storage.currency,
          unit: t(`storage.unit.${storage.unit}`),
          free: storage.free_days,
        })}
      </p>

      {storage.capped && (
        <p className="text-xs font-body text-navy/70 border-t border-amber/30 pt-2">
          {t('storage.capped', { days: storage.max_paid_days })}
        </p>
      )}

      {charged ? (
        <div className="border-t border-amber/30 pt-2 flex justify-between gap-4">
          <span className="text-xs font-body text-navy/50">
            {t(
              charged.state === 'accepted'
                ? 'storage.chargedAgreed'
                : 'storage.chargedPending',
            )}
          </span>
          <MonoText className="text-xs text-navy">
            {charged.amount === null
              ? t('storage.chargedDays', { days: charged.days })
              : `${charged.amount} ${charged.currency}`}
          </MonoText>
        </div>
      ) : (
        /* The counter is what it is: a notice. Saying so beside it is cheaper
           than a dispute about a number nobody promised. */
        <p className="text-[11px] font-body text-navy/40 border-t border-amber/30 pt-2">
          {t('storage.advisory')}
        </p>
      )}
    </div>
  )
}
