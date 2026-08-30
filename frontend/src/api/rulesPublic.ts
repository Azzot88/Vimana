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

export interface PublicQuestion {
  anchor: string
  question: string
  /** Markdown. Short by design — the section behind it carries the citation. */
  answer: string
  /** The section this answer compresses. Rendered as a link down to it: an
   *  answer with nothing behind it would be us asserting somebody else's law
   *  on our own authority. */
  section_anchor: string
  locale: string
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
  /** Something on the page is not in the readers language. */
  fallback_locale: boolean
  locale: string
  /** What the editor said when publishing this version — the "what changed"
   *  line. Empty is the common case for a first version and reads as silence. */
  published_note: string
  /** The compact reading of the same corpus, first on the page. */
  questions: PublicQuestion[]
  sections: PublicSection[]
  requirements: PublicRequirement[]
}

export interface QuestionPreview {
  anchor: string
  question: string
  locale: string
}

export interface RuleIndexEntry {
  category_key: string
  direction: RuleDirection
  jurisdiction_code: string
  jurisdiction_name: string
  title: string
  version: number
  /** Set at publication, so for the directory this is the date the version
   *  went live — what the chronological order sorts by. */
  reviewed_at: string | null
  /** "What changed". Makes the entry read as an entry rather than a menu item;
   *  empty for a first version, which is silence and not a gap. */
  published_note: string
  /** Served by the API, never assembled here: the prerender step writes one
   *  file per path, and a path built in two places differs in one of them. */
  path: string
  /** How many questions this corridor answers. Zero is a real answer. */
  question_count: number
  /** The questions themselves, text only. The directory shows real questions
   *  rather than a count of them: somebody who does not know the taxonomy
   *  still knows their own question. Also what the search field searches. */
  questions: QuestionPreview[]
}

export const rulesIndex = (locale: string) =>
  api.get<RuleIndexEntry[]>('/api/rules', { params: { locale } })

export const readRule = (
  category: string,
  direction: string,
  country: string,
  locale: string,
) =>
  api.get<PublicRuleSet>(`/api/rules/${category}/${direction}/${country}`, {
    params: { locale },
  })
