import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  corridorDemand,
  fileRequest,
  myRequests,
  updateRequest,
  type CorridorDemand,
  type SenderRequest,
} from '../api/requests'
import AirportSelect from '../components/AirportSelect'
import MonoText from '../components/MonoText'
import { usePrefs } from '../hooks/usePrefs'

/** T3.11.19 — «кто летит в ближайшие дни ЛА — Москва?», as a screen.
 *
 *  **366 posts in the market dump take this shape**, and they are not people
 *  failing to use the board. At a five-day median horizon the sender is right:
 *  at the moment they look, the trip they need does not exist yet. A listing
 *  answers a question about the present; this answers one about next week.
 *
 *  **Four fields and no more.** Category, weight and declared value are absent
 *  on purpose — the question being asked is whether anybody flies this corridor
 *  at all, and a form demanding a declared value before that is answered is a
 *  form nobody fills in. Those decisions belong to the deal, which is a later
 *  conversation with a person who exists.
 *
 *  **The demand list carries no names.** A carrier weighing a route needs the
 *  number; who asked is the senders' business, and publishing it would turn a
 *  request into a lead list somebody works through.
 *
 *  Functions (PROJECT §6.2a):
 *  - `RequestsPage()` — default export. Called by: `App` at `/requests`.
 */
export default function RequestsPage() {
  const { t } = useTranslation()
  const prefs = usePrefs()

  const [mine, setMine] = useState<SenderRequest[]>([])
  const [demand, setDemand] = useState<CorridorDemand[]>([])
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [from, setFrom] = useState(today(0))
  const [until, setUntil] = useState(today(14))
  const [what, setWhat] = useState('')
  const [notify, setNotify] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = () => {
    myRequests()
      .then(({ data }) => setMine(data))
      .catch(() => setMine([]))
    corridorDemand()
      .then(({ data }) => setDemand(data))
      .catch(() => setDemand([]))
  }

  useEffect(load, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await fileRequest({
        origin,
        destination,
        window_from: from,
        window_to: until,
        what: what.trim() || null,
        notify,
      })
      setWhat('')
      load()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : t('requests.failed'))
    } finally {
      setBusy(false)
    }
  }

  const flip = async (row: SenderRequest, patch: { is_open?: boolean; notify?: boolean }) => {
    try {
      await updateRequest(row.id, patch)
      load()
    } catch {
      setError(t('requests.failed'))
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="font-display font-semibold text-2xl text-navy">
          {t('requests.title')}
        </h1>
        {/* DESIGNGUIDELINES §9b — what this does, and what it is not. */}
        <p className="text-sm font-body text-navy/60 mt-1">{t('requests.lead')}</p>
      </div>

      <form
        onSubmit={submit}
        className="bg-white rounded-card border border-navy/10 p-4 space-y-3"
      >
        <div className="flex flex-wrap gap-3">
          <div className="flex-1 min-w-[9rem]">
            <span className="block text-xs font-body text-navy/40 mb-1">
              {t('requests.from')}
            </span>
            <AirportSelect value={origin} onChange={setOrigin} />
          </div>
          <div className="flex-1 min-w-[9rem]">
            <span className="block text-xs font-body text-navy/40 mb-1">
              {t('requests.to')}
            </span>
            <AirportSelect value={destination} onChange={setDestination} />
          </div>
        </div>

        {/* A window, not a date. «В ближайшие дни» is the actual request, and a
            single date would force a precision the sender does not have — then
            miss a trip leaving the day before. */}
        <div className="flex flex-wrap gap-3">
          <label className="flex-1 min-w-[9rem]">
            <span className="block text-xs font-body text-navy/40 mb-1">
              {t('requests.windowFrom')}
            </span>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="w-full px-3 py-2 rounded-field border border-navy/15 font-body text-sm"
            />
          </label>
          <label className="flex-1 min-w-[9rem]">
            <span className="block text-xs font-body text-navy/40 mb-1">
              {t('requests.windowTo')}
            </span>
            <input
              type="date"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
              className="w-full px-3 py-2 rounded-field border border-navy/15 font-body text-sm"
            />
          </label>
        </div>

        <label className="block">
          <span className="block text-xs font-body text-navy/40 mb-1">
            {t('requests.what')}
          </span>
          <input
            value={what}
            onChange={(e) => setWhat(e.target.value)}
            placeholder={t('requests.whatPlaceholder') as string}
            className="w-full px-3 py-2 rounded-field border border-navy/15 font-body text-sm"
          />
          <span className="block text-[11px] font-body text-navy/40 mt-1">
            {t('requests.whatHint')}
          </span>
        </label>

        <label className="flex items-center gap-2 text-xs font-body text-navy/70">
          <input
            type="checkbox"
            checked={notify}
            onChange={(e) => setNotify(e.target.checked)}
          />
          {t('requests.notify')}
        </label>

        {error && <p className="text-xs font-mono text-danger">{error}</p>}
        <button
          type="submit"
          disabled={busy || !origin || !destination}
          className="bg-navy text-ivory font-display font-medium text-sm px-4 py-2 min-h-[2.75rem] rounded-field hover:bg-navy-mid disabled:opacity-50"
        >
          {busy ? t('common.loading') : t('requests.submit')}
        </button>
      </form>

      {mine.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-display font-semibold text-sm text-navy/50 uppercase tracking-wide">
            {t('requests.mine')}
          </h2>
          <ul className="space-y-2">
            {mine.map((row) => (
              <li
                key={row.id}
                className={`rounded-card border p-4 space-y-1 ${
                  row.is_open ? 'border-navy/10 bg-white' : 'border-navy/10 bg-navy/[0.03]'
                }`}
              >
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <MonoText className="text-sm text-navy">
                    {row.origin} → {row.destination}
                  </MonoText>
                  <span className="text-xs font-body text-navy/50">
                    {prefs.date(row.window_from)} — {prefs.date(row.window_to)}
                  </span>
                </div>
                {row.what && (
                  <p className="text-xs font-body text-navy/60">{row.what}</p>
                )}
                <div className="flex flex-wrap gap-3 pt-1">
                  {/* Two switches and not one: «закрыл» and «не пишите мне» are
                      different answers, and a request kept open without letters
                      is still a public statement that somebody wants this
                      corridor. */}
                  <button
                    type="button"
                    onClick={() => flip(row, { notify: !row.notify })}
                    className="text-xs font-body text-navy/50 hover:text-navy"
                  >
                    {row.notify ? t('requests.mute') : t('requests.unmute')}
                  </button>
                  <button
                    type="button"
                    onClick={() => flip(row, { is_open: !row.is_open })}
                    className="text-xs font-body text-navy/50 hover:text-navy"
                  >
                    {row.is_open ? t('requests.close') : t('requests.reopen')}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {demand.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-display font-semibold text-sm text-navy/50 uppercase tracking-wide">
            {t('requests.demand')}
          </h2>
          <p className="text-[11px] font-body text-navy/40">
            {t('requests.demandHint')}
          </p>
          <ul className="flex flex-wrap gap-2">
            {demand.map((row) => (
              <li
                key={`${row.origin}-${row.destination}`}
                className="rounded-field border border-navy/10 bg-white px-3 py-2"
              >
                <MonoText className="text-xs text-navy">
                  {row.origin} → {row.destination}
                </MonoText>
                <span className="ml-2 text-xs font-body text-navy/50">
                  {t('requests.waiting', { count: row.waiting })}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

/** `YYYY-MM-DD`, `days` from now. Local, because a window is about the days a
 *  person is thinking in, not about UTC. */
function today(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}
