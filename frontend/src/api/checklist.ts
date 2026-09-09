import api from './client'

/** T3.11.06 — the checklist wizard's client.
 *
 *  Public, like the directory it reads (`MASTERPLAN §4.1`): a sign-up wall in
 *  front of free information is a sign-up form pretending to be a service. The
 *  same call works signed in, and then the saved case gains an owner.
 */
export interface ChecklistItem {
  code: string
  title: string
  issuer: string
  obtained_by: 'sender' | 'carrier' | 'recipient'
  is_mandatory: boolean
  valid_for_days: number | null
  lead_time_days: number | null
  /** Which jurisdiction asks for it. Shown because «кто этого требует» is the
   *  first thing anybody disputes, and a merged list that cannot say loses. */
  jurisdiction_code: string
  direction: 'export' | 'import' | 'transit'
  rule_set_id: string
  /** The last day this can be started and still arrive in time. `null` when no
   *  departure was given — «когда-нибудь» has no deadline. */
  start_by: string | null
  /** Already behind us. The one red line on the screen, and not a rarity: the
   *  median horizon on this market is five days. */
  too_late: boolean
  /** In the list *because* an answer is missing (`IMPLEMENTATIONPLAN §3.11.6`
   *  decides strictly). Reads «уточните», never «обязательно». */
  undecided: boolean
}

export interface Checklist {
  items: ChecklistItem[]
  /** `{code: [attribute, …]}` — the next question, not an error. */
  unanswered: Record<string, string[]>
  /** Every attribute the corridor's rules mention. The questionnaire is
   *  computed from the corpus, so a rule that grows a clause grows the form. */
  asks: string[]
  corridor: string[]
}

export interface ChecklistQuery {
  origin: string
  destination: string
  category: string
  transit?: string[]
  attrs?: Record<string, unknown>
  depart_at?: string | null
}

export interface ComplianceCase extends ChecklistQuery {
  id: string
  category_key: string
  checklist: Checklist
  trip_id?: string | null
  deal_id?: string | null
}

export const buildChecklist = (body: ChecklistQuery) =>
  api.post<Checklist>('/api/checklist', body)

export const saveCase = (body: ChecklistQuery & { deal_id?: string }) =>
  api.post<ComplianceCase>('/api/checklist/cases', body)

export const getCase = (caseId: string) =>
  api.get<ComplianceCase>(`/api/checklist/cases/${caseId}`)

/** T3.11.09 — the same list inside a deal, with the ticks derived from what has
 *  actually been filed. Parties only. */
export interface DealChecklistItem extends ChecklistItem {
  attached: boolean
  attachment_count: number
}

export interface DealChecklist {
  case_id: string | null
  items: DealChecklistItem[]
  unanswered: Record<string, string[]>
  corridor: string[]
  open_mandatory: number
}

export const getDealChecklist = (dealId: string) =>
  api.get<DealChecklist>(`/api/deals/${dealId}/checklist`)

/** T3.11.06 / T3.11.07 — what a corridor asks of one cargo, addressed by
 *  airport codes because that is what a trip is written in.
 *
 *  **One shape for two readings.** The trip form wants the whole list («что
 *  требуется, если я беру такой груз»); the board wants one red line («не
 *  успеваете»). Same computation, so the summary travels with the items rather
 *  than living behind a second endpoint that would need keeping in step.
 *
 *  `covered` is the difference between «мы про этот коридор ничего не написали»
 *  and «ничего не требуется». Printing the second where the first is true would
 *  be the platform vouching for rules it has never read. */
export interface CorridorForTrip {
  items: ChecklistItem[]
  too_late: number
  worst_days: number | null
  worst_title: string | null
  corridor: string[]
  covered: boolean
}

export const corridorForTrip = (params: {
  origin: string
  destination: string
  category: string
  depart_at?: string
}) => api.get<CorridorForTrip>('/api/checklist/for-trip', { params })
