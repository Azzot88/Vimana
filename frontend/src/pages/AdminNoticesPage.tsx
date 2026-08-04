import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import {
  createPlatformNotice,
  createRouteNote,
  deletePlatformNotice,
  deleteRouteNote,
  listPlatformNotices,
  listRouteNotes,
  type PlatformNotice,
  type RouteNote,
} from '../api/notices'
import MonoText from '../components/MonoText'

/** T_UX.2 pt.2 — superuser CRUD for RouteNote + PlatformNotice.
 *  Minimal admin UI — form + list + delete. Full editorial workflow
 *  (drafts, i18n backfill, active-until picker) — pt.3. */
export default function AdminNoticesPage() {
  const me = useAuthStore((s) => s.user)
  const [routeNotes, setRouteNotes] = useState<RouteNote[]>([])
  const [platformNotices, setPlatformNotices] = useState<PlatformNotice[]>([])
  const [error, setError] = useState('')

  // Form state — RouteNote
  const [rnOrigin, setRnOrigin] = useState('')
  const [rnDestination, setRnDestination] = useState('')
  const [rnStatus, setRnStatus] = useState<RouteNote['status']>('attention')
  const [rnSeverity, setRnSeverity] = useState<RouteNote['severity']>('info')
  const [rnHeadline, setRnHeadline] = useState('')
  const [rnBody, setRnBody] = useState('')

  // Form state — PlatformNotice
  const [pnKey, setPnKey] = useState('')
  const [pnSeverity, setPnSeverity] = useState<PlatformNotice['severity']>('info')
  const [pnSurface, setPnSurface] = useState<PlatformNotice['target_surface']>('all')
  const [pnHeadline, setPnHeadline] = useState('')
  const [pnBody, setPnBody] = useState('')

  if (me?.role !== 'superuser') return <Navigate to="/dashboard" replace />

  const reload = async () => {
    setError('')
    try {
      const [rn, pn] = await Promise.all([
        listRouteNotes(),
        listPlatformNotices(),
      ])
      setRouteNotes(rn.data)
      setPlatformNotices(pn.data)
    } catch {
      setError('Failed to load notices')
    }
  }

  useEffect(() => {
    reload()
  }, [])

  const submitRouteNote = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await createRouteNote({
        origin_iso: rnOrigin,
        destination_iso: rnDestination,
        status: rnStatus,
        severity: rnSeverity,
        headline: rnHeadline,
        body: rnBody,
      })
      setRnOrigin('')
      setRnDestination('')
      setRnHeadline('')
      setRnBody('')
      await reload()
    } catch {
      setError('Create route note failed')
    }
  }

  const submitPlatformNotice = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await createPlatformNotice({
        key: pnKey,
        severity: pnSeverity,
        target_surface: pnSurface,
        headline: pnHeadline,
        body: pnBody,
      })
      setPnKey('')
      setPnHeadline('')
      setPnBody('')
      await reload()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Create platform notice failed')
    }
  }

  return (
    <div className="space-y-8">
      <h1 className="font-display font-bold text-2xl text-navy">Notices</h1>
      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      <section className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
        <h2 className="font-display font-semibold text-lg text-navy">Route notes</h2>
        <form onSubmit={submitRouteNote} className="grid grid-cols-2 md:grid-cols-6 gap-2">
          <input
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-mono"
            placeholder="Origin (ISO or *)"
            value={rnOrigin}
            onChange={(e) => setRnOrigin(e.target.value)}
            required
          />
          <input
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-mono"
            placeholder="Dest (ISO or *)"
            value={rnDestination}
            onChange={(e) => setRnDestination(e.target.value)}
            required
          />
          <select
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-mono"
            value={rnStatus}
            onChange={(e) => setRnStatus(e.target.value as RouteNote['status'])}
          >
            <option value="standard">standard</option>
            <option value="attention">attention</option>
            <option value="complex">complex</option>
            <option value="restricted">restricted</option>
          </select>
          <select
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-mono"
            value={rnSeverity}
            onChange={(e) => setRnSeverity(e.target.value as RouteNote['severity'])}
          >
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="alert">alert</option>
          </select>
          <input
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-body col-span-2 md:col-span-6"
            placeholder="Headline (shown to users)"
            value={rnHeadline}
            onChange={(e) => setRnHeadline(e.target.value)}
            required
          />
          <textarea
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-body col-span-2 md:col-span-6"
            placeholder="Body — full description (optional)"
            rows={3}
            value={rnBody}
            onChange={(e) => setRnBody(e.target.value)}
          />
          <button
            type="submit"
            className="col-span-2 md:col-span-6 bg-navy text-ivory font-display font-medium text-xs py-2 rounded"
          >
            Create route note
          </button>
        </form>

        <div className="border-t border-navy/5 pt-3 space-y-1">
          {routeNotes.length === 0 && (
            <p className="text-xs font-body text-muted">No route notes yet.</p>
          )}
          {routeNotes.map((n) => (
            <div key={n.id} className="flex items-center justify-between text-xs font-mono">
              <span className="text-navy">
                {n.origin_iso}→{n.destination_iso}
                <span className="ml-2 text-muted">
                  [{n.status}/{n.severity}]
                </span>
                <span className="ml-2 text-muted font-body">{n.headline}</span>
              </span>
              <button
                onClick={async () => {
                  if (confirm(`Delete route note ${n.origin_iso}→${n.destination_iso}?`)) {
                    await deleteRouteNote(n.id)
                    await reload()
                  }
                }}
                className="text-danger hover:underline"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
        <h2 className="font-display font-semibold text-lg text-navy">Platform notices</h2>
        <form onSubmit={submitPlatformNotice} className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <input
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-mono col-span-2"
            placeholder="Slug key (unique, e.g. beta.disclaimer)"
            value={pnKey}
            onChange={(e) => setPnKey(e.target.value)}
            required
          />
          <select
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-mono"
            value={pnSeverity}
            onChange={(e) => setPnSeverity(e.target.value as PlatformNotice['severity'])}
          >
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="alert">alert</option>
          </select>
          <select
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-mono"
            value={pnSurface}
            onChange={(e) => setPnSurface(e.target.value as PlatformNotice['target_surface'])}
          >
            <option value="all">all</option>
            <option value="footer">footer</option>
            <option value="trip_card">trip_card</option>
            <option value="deal_page">deal_page</option>
          </select>
          <input
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-body col-span-2 md:col-span-4"
            placeholder="Headline (shown to users)"
            value={pnHeadline}
            onChange={(e) => setPnHeadline(e.target.value)}
            required
          />
          <textarea
            className="border border-navy/20 rounded px-2 py-1.5 text-xs font-body col-span-2 md:col-span-4"
            placeholder="Body (optional)"
            rows={2}
            value={pnBody}
            onChange={(e) => setPnBody(e.target.value)}
          />
          <button
            type="submit"
            className="col-span-2 md:col-span-4 bg-navy text-ivory font-display font-medium text-xs py-2 rounded"
          >
            Create platform notice
          </button>
        </form>

        <div className="border-t border-navy/5 pt-3 space-y-1">
          {platformNotices.length === 0 && (
            <p className="text-xs font-body text-muted">No platform notices yet.</p>
          )}
          {platformNotices.map((n) => (
            <div key={n.id} className="flex items-center justify-between text-xs font-mono">
              <span className="text-navy">
                <MonoText className="inline">{n.key}</MonoText>
                <span className="ml-2 text-muted">
                  [{n.severity}/{n.target_surface}]
                </span>
                <span className="ml-2 text-muted font-body">{n.headline}</span>
              </span>
              <button
                onClick={async () => {
                  if (confirm(`Delete platform notice ${n.key}?`)) {
                    await deletePlatformNotice(n.id)
                    await reload()
                  }
                }}
                className="text-danger hover:underline"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
