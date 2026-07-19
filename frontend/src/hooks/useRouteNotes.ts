import { useEffect, useState } from 'react'
import { listRouteNotes, type RouteNote } from '../api/notices'

/** T_UX.2 pt.3 — fetch active RouteNotes. If both `origin` and `destination`
 *  are omitted, fetches ALL active notes (useful for a listing page that
 *  filters per-card locally). */
export function useRouteNotes(origin?: string, destination?: string) {
  const [notes, setNotes] = useState<RouteNote[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    const params: Record<string, string> = {}
    if (origin) params.origin = origin
    if (destination) params.destination = destination
    listRouteNotes(params)
      .then(({ data }) => setNotes(data))
      .catch(() => setNotes([]))
      .finally(() => setLoading(false))
  }, [origin, destination])

  return { notes, loading }
}

/** Helper: filter notes to those matching a specific corridor.
 *  A note matches if origin_iso is '*' OR equals given origin, AND same for destination. */
export function filterNotesForCorridor(
  notes: RouteNote[],
  origin: string,
  destination: string,
): RouteNote[] {
  return notes.filter(
    (n) =>
      (n.origin_iso === '*' || n.origin_iso === origin) &&
      (n.destination_iso === '*' || n.destination_iso === destination),
  )
}
