import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { AdminRulePreviewPage } from '../pages/AdminRulesPage'
import type { RulePreview } from '../api/rules'
import type { User } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T_RULES.7 — the editor's preview of a set in any status.
 *
 * Pinned: the page is the public corridor page fed from the editor's endpoint
 * (never the public one, which refuses drafts), it says what it is before
 * anything else, it does not offer the public `.md` link that would 404, and a
 * non-editor never gets as far as asking.
 */
vi.mock('../api/rules', async () => {
  const actual = await vi.importActual<typeof import('../api/rules')>('../api/rules')
  return { ...actual, previewRuleSet: vi.fn() }
})
vi.mock('../api/rulesPublic', async () => {
  const actual =
    await vi.importActual<typeof import('../api/rulesPublic')>('../api/rulesPublic')
  return { ...actual, readRule: vi.fn() }
})

import { previewRuleSet } from '../api/rules'
import { readRule } from '../api/rulesPublic'

const t = i18n.t.bind(i18n)

const as = (roles: string[]) =>
  ({ id: 'u-1', display_name: 'Ed', roles }) as unknown as User

const draft: RulePreview = {
  id: 's-1',
  category_key: 'medicine',
  direction: 'export',
  jurisdiction_code: 'XA',
  jurisdiction_name: 'Аркадия (вымышленная, тест)',
  title: '[ТЕСТ] Вывоз лекарств из Аркадии',
  version: 1,
  effective_from: '2026-10-04T00:00:00Z',
  reviewed_at: null,
  checked_at: null,
  needs_review: false,
  fallback_locale: false,
  locale: 'ru',
  published_note: '',
  questions: [],
  sections: [
    {
      anchor: 'banned',
      title: 'Запрещено к вывозу',
      body: 'Из Аркадии **нельзя вывезти** аркадин.',
      locale: 'ru',
      sources: [],
    },
  ],
  requirements: [],
  status: 'draft',
}

const show = () =>
  renderWithProviders(
    <Routes>
      <Route path="/admin/rules/:setId/preview" element={<AdminRulePreviewPage />} />
      <Route path="/dashboard" element={<p>dashboard</p>} />
    </Routes>,
    { route: '/admin/rules/s-1/preview' },
  )

describe('AdminRulePreviewPage', () => {
  beforeEach(() => {
    vi.mocked(previewRuleSet).mockReset()
    vi.mocked(readRule).mockReset()
  })

  it('renders a draft from the editor endpoint, under a banner, without the public file link', async () => {
    useAuthStore.getState().setAuth(as(['compliance_editor']), 'token-1')
    vi.mocked(previewRuleSet).mockResolvedValue({ data: draft } as never)
    show()

    // As a heading: the same title is also a link in the contents rail.
    expect(
      await screen.findByRole('heading', { name: 'Запрещено к вывозу' }),
    ).toBeInTheDocument()
    expect(previewRuleSet).toHaveBeenCalledWith('s-1', i18n.language)
    expect(readRule).not.toHaveBeenCalled()
    expect(
      screen.getByText(
        t('rulesPage.previewBanner', { status: t('adminRules.status.draft') }),
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText(t('rulesPage.downloadMd'))).not.toBeInTheDocument()
  })

  it('sends a non-editor to the panel without asking for the draft', async () => {
    useAuthStore.getState().setAuth(as([]), 'token-1')
    show()

    expect(await screen.findByText('dashboard')).toBeInTheDocument()
    expect(previewRuleSet).not.toHaveBeenCalled()
  })

  it('says the corridor is missing when the set does not exist', async () => {
    useAuthStore.getState().setAuth(as(['superuser']), 'token-1')
    vi.mocked(previewRuleSet).mockRejectedValue({ response: { status: 404 } })
    show()

    expect(await screen.findByText(t('rulesPage.missingTitle'))).toBeInTheDocument()
  })
})
