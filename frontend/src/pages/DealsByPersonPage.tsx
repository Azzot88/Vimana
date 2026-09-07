import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { listDeals, type Deal } from '../api/deals'
import { listMyInquiries } from '../api/inquiry'
import DealCard from '../components/DealCard'
import MonoText from '../components/MonoText'

/** T3.11.26 — every deal, grouped by the person it is with.
 *
 *  Owner's request 2026-09-07: «нужна отдельная страница сделок, где можно
 *  выбрать одного пользователя и зайти в любую из сделок».
 *
 *  It is the other door into the same thing `T3.11.23` builds from the chat
 *  side: one chat per person, several deals inside it. Here you start from the
 *  person; there you start from the conversation. Both have to exist, because
 *  «мои сделки с Игорем» and «о чём мы с Игорем говорили» are two different
 *  questions people arrive with.
 *
 *  `/history` is not this. It stayed what `T_UX.18` made it — the archive you
 *  look something up in, flat and reverse-chronological. This one is for
 *  choosing.
 *
 *  Functions (PROJECT §6.2a):
 *  - `DealsByPersonPage()` — default export. Called by: the `/deals` route.
 */
type SortKey = 'recent' | 'count'

export default function DealsByPersonPage() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [deals, setDeals] = useState<Deal[]>([])
  const [chats, setChats] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [sort, setSort] = useState<SortKey>('recent')
  const [openFor, setOpenFor] = useState<string | null>(null)

  useEffect(() => {
    listDeals({ limit: 100 })
      .then((r) => setDeals(r.data.items))
      .catch(() => setDeals([]))
      .finally(() => setLoading(false))
    /* T3.11.23 — the person's chat, by person. This page **is** the contact
       list until `T3.11.24` builds one, and «зайти в чат можно только через
       контакт человека» needs a door somewhere. A chat that fails to load
       costs the button, not the page: the deals are what you came for. */
    listMyInquiries()
      .then((r) =>
        setChats(
          Object.fromEntries(r.data.map((c) => [c.carrier_id, c.id])),
        ),
      )
      .catch(() => setChats({}))
  }, [])

  /** The counterparty of a deal — whoever is not me. A deal always has both a
   *  sender and a carrier, and exactly one of them is the reader. */
  const other = (deal: Deal) =>
    deal.carrier_id === user?.id
      ? { id: deal.sender_id, name: deal.sender_name }
      : { id: deal.carrier_id, name: deal.carrier_name }

  const groups = useMemo(() => {
    const by = new Map<string, { id: string; name: string; deals: Deal[] }>()
    for (const deal of deals) {
      const person = other(deal)
      const existing = by.get(person.id)
      if (existing) {
        existing.deals.push(deal)
        continue
      }
      by.set(person.id, {
        id: person.id,
        // A name the server did not send is not rendered as a blank row: the
        // short id is ugly and honest, and it is what the person can still
        // paste into a message to ask who this was.
        name: person.name || person.id.slice(0, 8),
        deals: [deal],
      })
    }
    const list = [...by.values()]
    // `created_at` is ISO-8601, so string comparison is chronological — no Date
    // objects built for a sort of a hundred rows.
    for (const g of list) {
      g.deals.sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    }
    if (sort === 'count') {
      list.sort((a, b) => b.deals.length - a.deals.length)
    } else {
      list.sort((a, b) =>
        a.deals[0].created_at < b.deals[0].created_at ? 1 : -1,
      )
    }
    return list
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deals, sort, user?.id])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-navy/40 text-sm">{t('common.loading')}</MonoText>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display font-bold text-2xl text-navy">
          {t('deals.byPersonTitle')}
        </h1>
        <div className="flex items-center gap-2">
          {(['recent', 'count'] as const).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={sort === key}
              onClick={() => setSort(key)}
              className={`px-3 py-2 min-h-[2.75rem] rounded-field border text-xs font-body transition-colors ${
                sort === key
                  ? 'border-cyan bg-cyan/5 text-cyan'
                  : 'border-navy/15 text-navy/60 hover:border-navy/40'
              }`}
            >
              {t(`deals.sortBy.${key}`)}
            </button>
          ))}
        </div>
      </div>

      {groups.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-sm font-body text-navy/40">{t('deals.noDeals')}</p>
          <Link
            to="/send"
            className="inline-block mt-3 text-sm text-cyan hover:underline font-body"
          >
            {t('nav.trips')}
          </Link>
        </div>
      ) : (
        <div className="grid gap-3">
          {groups.map((group) => {
            const open = openFor === group.id
            return (
              <div
                key={group.id}
                className="bg-white rounded-card border border-navy/10 overflow-hidden"
              >
                <div className="flex items-center gap-1 pr-3">
                  <button
                    type="button"
                    onClick={() => setOpenFor(open ? null : group.id)}
                    aria-expanded={open}
                    className="flex-1 flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-ivory transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-body font-medium text-navy truncate">
                        {group.name}
                      </p>
                      <p className="text-xs font-body text-navy/45">
                        {t('deals.countWithPerson', { count: group.deals.length })}
                      </p>
                    </div>
                    <MonoText className="text-navy/30 shrink-0">
                      {open ? '−' : '+'}
                    </MonoText>
                  </button>
                  {/* T3.11.23 — the way into the conversation with this person.
                      It sits beside the expander rather than inside it: a link
                      nested in a button is neither, and keyboards prove it
                      first. Shown only when a chat exists — one is created by
                      writing or by starting a deal, never by looking. */}
                  {chats[group.id] && (
                    <Link
                      to={`/chats/${chats[group.id]}`}
                      className="shrink-0 px-3 py-2 min-h-[2.75rem] flex items-center rounded-field border border-navy/15 text-xs font-body text-navy/60 hover:border-cyan hover:text-cyan transition-colors"
                    >
                      {t('inquiry.chatButton')}
                    </Link>
                  )}
                </div>

                {open && (
                  <div className="border-t border-navy/10 p-3 grid gap-2 bg-ivory/40">
                    {/* The same card the chat draws: one deal looks like one
                        deal wherever it is listed. */}
                    {group.deals.map((deal) => (
                      <DealCard key={deal.id} deal={deal} />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
