import type { DealRole } from './cardForms'

/** T3.12.01 — who the reader is in a deal, answered in one place.
 *
 *  Every screen used to ask it its own way — `carrier_id === me ? carrier :
 *  sender` — and every one of those answers was wrong for exactly one person:
 *  the recipient, who came out as a «sender» in lists and as nobody on the deal
 *  screen, which is why the delivery the server addressed to them had no button
 *  (разбор 2026-09-13).
 *
 *  The server's own answer lives in `core/deal_access.party_role`, and the two
 *  read the deal in the same order: a sender who named themselves the recipient
 *  is the sender, because that is the role that owes decisions.
 *
 *  Functions (PROJECT §6.2a):
 *  - `roleIn(deal, userId)` — `sender` | `carrier` | `recipient` | null.
 *    Called by: `pages/DealVaultPage`, `pages/DashboardPage`, `pages/DealsPage`,
 *    `pages/DealsByPersonPage`.
 */
export interface DealParties {
  sender_id: string
  carrier_id: string
  recipient_id?: string | null
}

export function roleIn(
  deal: DealParties | null | undefined,
  userId: string | null | undefined,
): DealRole | null {
  if (!deal || !userId) return null
  if (deal.sender_id === userId) return 'sender'
  if (deal.carrier_id === userId) return 'carrier'
  if (deal.recipient_id && deal.recipient_id === userId) return 'recipient'
  return null
}
