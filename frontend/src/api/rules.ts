import api from './client'

/** T3.11.02 — the rules editor's client. `import` is the wire value; the
 *  Python member is `import_` only because the word is a keyword there. */
export type RuleDirection = 'export' | 'import' | 'transit'
export type RuleStatus = 'draft' | 'review' | 'published' | 'outdated'
export type ObtainedBy = 'sender' | 'carrier' | 'recipient'

export interface RuleSource {
  id: string
  authority: string
  document_title: string
  document_date: string | null
  url: string
  /** Verbatim, and required. A paraphrase checks the text against whoever
   *  wrote it, which looks like proof and is not. */
  quote: string
}

export interface RuleSection {
  id: string
  anchor: string
  locale: string
  order: number
  title: string
  body: string
  sources: RuleSource[]
}

export interface RuleQuestion {
  id: string
  anchor: string
  locale: string
  order: number
  question: string
  /** Markdown, like a section body. Short by design. */
  answer: string
  /** The section this answer compresses. Checked at the publication gate: an
   *  answer pointing nowhere blocks the whole set. */
  section_anchor: string
}

export interface DocumentRequirement {
  id: string
  code: string
  title: string
  issuer: string
  obtained_by: ObtainedBy
  is_mandatory: boolean
  condition: Record<string, unknown> | null
  valid_for_days: number | null
  /** How long the paper takes to obtain. The checklist counts this backwards
   *  from the departure date — the one number a person cannot look up. */
  lead_time_days: number | null
  cost_estimate: number | null
  currency: string
  notes: string
}

export interface RuleSet {
  id: string
  direction: RuleDirection
  jurisdiction_code: string
  category_key: string
  version: number
  status: RuleStatus
  title: string
  effective_from: string
  reviewed_at: string | null
  checked_at: string | null
  needs_review: boolean
}

export interface RuleSetDetail extends RuleSet {
  questions: RuleQuestion[]
  sections: RuleSection[]
  requirements: DocumentRequirement[]
  /** Empty means publishable. Shown before the button is pressed, so the
   *  editor is not told what is wrong only by being refused. */
  blockers: string[]
}

export interface StatusEvent {
  id: string
  from_status: RuleStatus | null
  to_status: RuleStatus
  actor_id: string | null
  note: string
  created_at: string
}

export interface Jurisdiction {
  code: string
  kind: 'country' | 'subdivision' | 'city' | 'transit_point'
  parent_code: string | null
  name: string
}

export const listRuleSets = (params?: { status?: RuleStatus; category_key?: string }) =>
  api.get<RuleSet[]>('/api/admin/rules', { params })

export const createRuleSet = (body: {
  direction: RuleDirection
  jurisdiction_code: string
  category_key: string
  title?: string
}) => api.post<RuleSet>('/api/admin/rules', body)

export const getRuleSet = (id: string) =>
  api.get<RuleSetDetail>(`/api/admin/rules/${id}`)

export const patchRuleSet = (id: string, title: string) =>
  api.patch<RuleSet>(`/api/admin/rules/${id}`, { title })

export const deleteRuleSet = (id: string) =>
  api.delete<void>(`/api/admin/rules/${id}`)

export const changeRuleStatus = (id: string, to: RuleStatus, note = '') =>
  api.post<StatusEvent>(`/api/admin/rules/${id}/status`, { to, note })

export const ruleHistory = (id: string) =>
  api.get<StatusEvent[]>(`/api/admin/rules/${id}/history`)

export const addSection = (
  setId: string,
  body: { anchor: string; locale: string; order?: number; title?: string; body?: string },
) => api.post<RuleSection>(`/api/admin/rules/${setId}/sections`, body)

export const deleteSection = (sectionId: string) =>
  api.delete<void>(`/api/admin/rules/sections/${sectionId}`)

export const addSource = (
  sectionId: string,
  body: { authority: string; document_title: string; url?: string; quote: string },
) => api.post<RuleSource>(`/api/admin/rules/sections/${sectionId}/sources`, body)

export const deleteSource = (sourceId: string) =>
  api.delete<void>(`/api/admin/rules/sources/${sourceId}`)

export const addRequirement = (
  setId: string,
  body: {
    code: string
    title: string
    issuer?: string
    obtained_by?: ObtainedBy
    lead_time_days?: number | null
    valid_for_days?: number | null
    condition?: Record<string, unknown> | null
    notes?: string
  },
) => api.post<DocumentRequirement>(`/api/admin/rules/${setId}/requirements`, body)

export const deleteRequirement = (reqId: string) =>
  api.delete<void>(`/api/admin/rules/requirements/${reqId}`)

export const addQuestion = (
  setId: string,
  body: {
    anchor: string
    locale: string
    order?: number
    question: string
    answer?: string
    section_anchor: string
  },
) => api.post<RuleQuestion>(`/api/admin/rules/${setId}/questions`, body)

export const patchQuestion = (
  questionId: string,
  body: {
    anchor: string
    locale: string
    order?: number
    question: string
    answer?: string
    section_anchor: string
  },
) => api.patch<RuleQuestion>(`/api/admin/rules/questions/${questionId}`, body)

export const deleteQuestion = (questionId: string) =>
  api.delete<void>(`/api/admin/rules/questions/${questionId}`)

export const listJurisdictions = () =>
  api.get<Jurisdiction[]>('/api/admin/jurisdictions')

export const patchSection = (
  sectionId: string,
  body: { anchor: string; locale: string; order?: number; title?: string; body?: string },
) => api.patch<RuleSection>(`/api/admin/rules/sections/${sectionId}`, body)

/** T3.11.02 pt.2 — a citation is the thing most likely to need correcting, and
 *  delete-and-recreate lost its identity for the sake of a typo. */
export const patchSource = (
  sourceId: string,
  body: { authority: string; document_title: string; url?: string; quote: string },
) => api.patch<RuleSource>(`/api/admin/rules/sources/${sourceId}`, body)

export const patchRequirement = (
  reqId: string,
  body: {
    code: string
    title: string
    issuer?: string
    obtained_by?: ObtainedBy
    lead_time_days?: number | null
    valid_for_days?: number | null
    condition?: Record<string, unknown> | null
    notes?: string
  },
) => api.patch<DocumentRequirement>(`/api/admin/rules/requirements/${reqId}`, body)
