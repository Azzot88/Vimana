import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import AdminRoleJournalPage from '../pages/AdminRoleJournalPage'
import type { RoleGrant } from '../api/roles'
import type { User } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T_UX.25 — the journal reads back where a role came from.
 *
 * Pinned: a withdrawal is shown as plainly as a grant (the half that gets
 * forgotten), the platform is named when no person acted, and an account with
 * no history says so instead of drawing an empty table.
 */
vi.mock('../api/admin', async () => {
  const actual = await vi.importActual<typeof import('../api/admin')>('../api/admin')
  return { ...actual, roleJournal: vi.fn() }
})

import { roleJournal } from '../api/admin'

const t = i18n.t.bind(i18n)

const admin = {
  id: 'admin-1',
  display_name: 'Zero',
  roles: ['superuser'],
} as unknown as User

const grant = (over: Partial<RoleGrant>): RoleGrant => ({
  id: 'g1',
  role: 'arbiter',
  event: 'offered',
  actor_id: 'admin-1',
  actor_name: 'Zero',
  reason: 'нужен арбитр на коридор',
  created_at: '2026-09-10T10:00:00Z',
  ...over,
})

const show = () =>
  renderWithProviders(
    <Routes>
      <Route path="/admin/users/:userId/roles" element={<AdminRoleJournalPage />} />
    </Routes>,
    { route: '/admin/users/u-1/roles' },
  )

describe('AdminRoleJournalPage', () => {
  beforeEach(() => {
    vi.mocked(roleJournal).mockReset()
    useAuthStore.getState().setAuth(admin, 'token-1')
  })

  it('shows a withdrawal as plainly as a grant', async () => {
    vi.mocked(roleJournal).mockResolvedValue({
      data: [
        grant({ id: 'g3', event: 'revoked', reason: 'больше не работает с нами' }),
        grant({ id: 'g2', event: 'accepted', reason: '' }),
        grant({}),
      ],
    } as never)
    show()

    expect(await screen.findByText(t('adminJournal.events.revoked'))).toBeInTheDocument()
    expect(screen.getByText(t('adminJournal.events.accepted'))).toBeInTheDocument()
    expect(screen.getByText(t('adminJournal.events.offered'))).toBeInTheDocument()
    expect(screen.getByText('больше не работает с нами')).toBeInTheDocument()
  })

  it('names the platform when no person acted', async () => {
    vi.mocked(roleJournal).mockResolvedValue({
      data: [grant({ actor_id: null, actor_name: null })],
    } as never)
    show()

    expect(await screen.findByText(t('adminJournal.platform'))).toBeInTheDocument()
  })

  it('says an account has no history rather than drawing an empty table', async () => {
    vi.mocked(roleJournal).mockResolvedValue({ data: [] } as never)
    show()

    expect(await screen.findByText(t('adminJournal.empty'))).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('a failed request is said out loud, not drawn as an empty journal', async () => {
    vi.mocked(roleJournal).mockRejectedValue(new Error('no'))
    show()

    expect(await screen.findByText(t('adminJournal.loadFailed'))).toBeInTheDocument()
  })
})
