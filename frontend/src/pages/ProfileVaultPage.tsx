import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { listDeals, type Deal } from '../api/deals'
import { listMyFiles, type SafeFile } from '../api/dealvault'
import { usePrefs } from '../hooks/usePrefs'
import MonoText from '../components/MonoText'
import StatusBadge from '../components/StatusBadge'

/** T_UX.27 — the vault as a place, not as a picker.
 *
 *  Owner, 2026-09-15: «должна быть страница в личном кабинете, где виден личный
 *  сейф и сейфы сделок, в которых участвовал пользователь, с возможностью зайти
 *  и почитать, закрытые и активные».
 *
 *  Both halves existed and neither had a door. `UserFile` has been filled since
 *  T3.11.25, but the only way to see it was the attachment picker inside a
 *  deal; a deal's vault was reachable only while the deal was live, so a closed
 *  one took the whole record out of sight — the record DealVault exists for.
 *
 *  **Closed deals are listed, not hidden.** They are separated rather than
 *  filtered: «что было» and «что идёт» are different questions, and a list that
 *  answers only the second is the reason this page was needed.
 *
 *  Functions (PROJECT §6.2a):
 *  - `ProfileVaultPage()` — default export. Called by: `App` at `/profile/vault`.
 */
const CLOSED: Deal['status'][] = ['closed', 'cancelled']

function size(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

export default function ProfileVaultPage() {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const [deals, setDeals] = useState<Deal[]>([])
  const [files, setFiles] = useState<SafeFile[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      // Both halves of the page, and neither blocks the other: a safe with no
      // files is still a page about deals.
      const [dealsResult, filesResult] = await Promise.allSettled([
        listDeals({ limit: 100 }),
        listMyFiles(),
      ])
      if (dealsResult.status === 'fulfilled') setDeals(dealsResult.value.data.items)
      if (filesResult.status === 'fulfilled') setFiles(filesResult.value.data)
      setLoading(false)
    }
    void load()
  }, [])

  const active = deals.filter((d) => !CLOSED.includes(d.status))
  const closed = deals.filter((d) => CLOSED.includes(d.status))

  const dealRow = (deal: Deal) => (
    <Link
      key={deal.id}
      to={`/deals/${deal.id}/vault`}
      className="bg-white rounded-card border border-navy/10 p-4 hover:border-cyan/40 transition-colors flex items-center justify-between gap-3"
    >
      <div className="space-y-1 min-w-0">
        <MonoText className="text-sm text-navy font-medium">
          {deal.origin && deal.destination
            ? `${deal.origin} → ${deal.destination}`
            : (deal.deal_no ?? deal.shipment_no ?? deal.id.slice(0, 8))}
        </MonoText>
        <p className="text-xs font-body text-navy/50 truncate">
          {deal.deal_no ?? deal.shipment_no} {deal.cargo_description}
        </p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <StatusBadge status={deal.status} />
        <span className="text-xs font-body text-cyan">{t('vault.open')}</span>
      </div>
    </Link>
  )

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display font-bold text-xl text-navy">{t('vault.title')}</h1>
        <p className="text-sm font-body text-navy/50 mt-1">{t('vault.lead')}</p>
      </div>

      {loading ? (
        <p className="text-sm font-body text-navy/40 text-center py-8">
          {t('common.loading')}
        </p>
      ) : (
        <>
          <section className="space-y-3">
            <h2 className="font-display font-semibold text-lg text-navy">
              {t('vault.dealsTitle')}
            </h2>
            {deals.length === 0 ? (
              <p className="text-sm font-body text-navy/40">{t('vault.noDeals')}</p>
            ) : (
              <>
                {active.length > 0 && (
                  <>
                    <h3 className="text-xs font-display font-semibold text-navy/45 uppercase tracking-wide">
                      {t('vault.active')}
                    </h3>
                    <div className="grid gap-3">{active.map(dealRow)}</div>
                  </>
                )}
                {closed.length > 0 && (
                  <>
                    <h3 className="text-xs font-display font-semibold text-navy/45 uppercase tracking-wide pt-2">
                      {t('vault.closed')}
                    </h3>
                    <div className="grid gap-3">{closed.map(dealRow)}</div>
                  </>
                )}
              </>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="font-display font-semibold text-lg text-navy">
              {t('vault.filesTitle')}
            </h2>
            {files.length === 0 ? (
              <p className="text-sm font-body text-navy/40">{t('vault.noFiles')}</p>
            ) : (
              <div className="bg-white rounded-card border border-navy/10 divide-y divide-navy/5">
                {files.map((file) => (
                  <div key={file.id} className="px-4 py-3 space-y-1">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="text-sm font-body text-navy">
                        {t(`chat.kind.${file.kind}`, file.kind)}
                      </span>
                      <MonoText className="text-xs text-navy/40">
                        {size(file.size_bytes)}
                      </MonoText>
                      <span className="text-xs font-body text-navy/45">
                        {t('vault.first', { date: prefs.dateTime(file.first_provided_at) })}
                      </span>
                      {file.url && (
                        <a
                          href={file.url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-xs font-body text-cyan hover:underline ml-auto"
                        >
                          {t('vault.openFile')}
                        </a>
                      )}
                    </div>
                    <p className="text-xs font-body text-navy/45">
                      {file.attached_to && file.attached_to.length > 0 ? (
                        <>
                          {t('vault.attached')}{' '}
                          {file.attached_to.map((ref, index) => (
                            <span key={ref.deal_id}>
                              {index > 0 && ', '}
                              <Link
                                to={`/deals/${ref.deal_id}/vault`}
                                className="text-cyan hover:underline"
                              >
                                {ref.deal_no ?? ref.deal_id.slice(0, 8)}
                              </Link>
                            </span>
                          ))}
                        </>
                      ) : (
                        t('vault.notAttached')
                      )}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
