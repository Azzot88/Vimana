import AudienceLanding from '../components/landing/AudienceLanding'

/**
 * T_UX.23 — `/business`, and the one audience page with no panel behind it.
 *
 * There is no "business mode": `active_mode` is `carrier | sender` and nothing
 * else. So unlike `/carrier` and `/send`, this address shows the same page to
 * everyone, signed in or not.
 *
 * **What this page may and may not say.** The B2B offer is real as a model —
 * `MASTERPLAN §4.1` поток C: per-kilo pricing with a volumetric floor, a pool of
 * bonded carriers, the platform's share — but **none of it is built**. No
 * business account, no invoices, no tracking, no API, no volume pricing, no
 * recurring shipments; cards are Фаза 4 and escrow Фаза 5, neither started.
 *
 * Therefore the page sells the *route*, which is true today (people already fly
 * these corridors and carry things), and asks for a conversation. It does not
 * list features. The owner chose this framing over a feature list on
 * 2026-08-23; the alternative would have needed "planned" stamped on every
 * line, which is a worse page and a worse promise.
 */
export default function BusinessLandingPage() {
  return <AudienceLanding audience="business" secondaryTo="/carrier" />
}
