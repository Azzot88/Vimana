import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import DealStages from '../components/DealStages'
import type { DealRole } from '../lib/cardForms'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T3.12.05 — the recipient does not open a dispute; they ask the sender to
 * (owner, 2026-09-13), and the request is a line the sender reads (2026-09-14).
 * Pinned: the recipient's form sends a `dispute.requested` card and never the
 * dispute itself, and the sender keeps the ordinary button.
 */
vi.mock('../api/terms', async () => {
  const actual = await vi.importActual<typeof import('../api/terms')>('../api/terms')
  return { ...actual, raiseCard: vi.fn() }
})
vi.mock('../api/admin', async () => {
  const actual = await vi.importActual<typeof import('../api/admin')>('../api/admin')
  return { ...actual, openDispute: vi.fn() }
})

import { raiseCard } from '../api/terms'
import { openDispute } from '../api/admin'

const t = i18n.t.bind(i18n)

const stages = (myRole: DealRole) => (
  <DealStages
    dealId="d1"
    status="in_transit"
    myRole={myRole}
    terms={null}
    deal={null}
    messages={[]}
    onDone={() => {}}
  />
)

beforeEach(() => {
  vi.mocked(raiseCard).mockReset().mockResolvedValue({} as never)
  vi.mocked(openDispute).mockReset().mockResolvedValue({} as never)
})

describe('the recipient and a dispute', () => {
  it('asks the sender instead of opening one', async () => {
    renderWithProviders(stages('recipient'))
    fireEvent.click(screen.getByText(t('stages.more')))
    expect(screen.queryByText(t('dispute.openButton'))).toBeNull()

    fireEvent.click(screen.getByText(t('disputeRequest.button')))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'the box is wet' } })
    fireEvent.click(screen.getByText(t('disputeRequest.submit')))

    await waitFor(() =>
      expect(raiseCard).toHaveBeenCalledWith(
        'd1',
        'dispute.requested',
        { reason: 'unpaid' },
        'the box is wet',
      ),
    )
    expect(openDispute).not.toHaveBeenCalled()
  })

  it('leaves the sender with the dispute itself', () => {
    renderWithProviders(stages('sender'))
    fireEvent.click(screen.getByText(t('stages.more')))
    expect(screen.getByText(t('dispute.openButton'))).toBeInTheDocument()
    expect(screen.queryByText(t('disputeRequest.button'))).toBeNull()
  })
})
