import api from './client'
import type { RuleDirection } from './rules'

/** T3.11.03 — the public directory. No session, no account: the free half of
 *  stream D (`MASTERPLAN §4.1`). */

export interface PublicSource {
  authority: string
  document_title: string
  document_date: string | null
  url: string
  /** Verbatim. The quotation is what makes the claim checkable. */
  quote: string
}

export interface PublicSection {
  anchor: string
  title: string
  body: string
  /** The locale this section was actually served in — not always the one
   *  asked for. A half-translated corpus is a real state. */
  locale: string
  sources: PublicSource[]
}

export interface PublicRequirement {
  code: string
  title: string
  issuer: string
  obtained_by: string
  is_mandatory: boolean
  condition: Record<string, unknown> | null
  valid_for_days: number | null
  /** Days to obtain. The checklist will count this backwards from departure. */
  lead_time_days: number | null
  notes: string
}

export interface PublicRuleSet {
  id: string
  category_key: string
  direction: RuleDirection
  jurisdiction_code: string
  jurisdiction_name: string
  title: string
  version: number
  effective_from: string
  /** A person checked this against the source on this date. */
  reviewed_at: string | null
  /** The watcher last looked at the source. Says nothing about the text. */
  checked_at: string | null
  needs_review: boolean
  /** Something on the page is not in the reader's language. */
  fallback_locale: boolean
  locale: string
  sections: PublicSection[]
  requirements: PublicRequirement[]
}

export interface RuleIndexEntry {
  category_key: string
  direction: RuleDirection
  jurisdiction_code: string
  jurisdiction_name: string
  title: string
  reviewed_at: string | null
  /** Served by the API, never assembled here: the prerender step writes one
   *  file per path, and a path built in two places differs in one of them. */
  path: string
}

export const rulesIndex = () => api.get<RuleIndexEntry[]>('/api/rules')

export const readRule = (
  category: string,
  direction: string,
  country: string,
  locale: string,
) =>
  api.get<PublicRuleSet>(`/api/rules/${category}/${direction}/${country}`, {
    params: { locale },
  })
