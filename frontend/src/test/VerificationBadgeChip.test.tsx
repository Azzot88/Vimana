import { describe, expect, it } from 'vitest'
import VerificationBadgeChip from '../components/VerificationBadgeChip'
import { renderWithProviders } from './render'

/**
 * T_TRUST.1 — "verified" is never rendered without "when" (`D-EVIDENCE-DECAYS`).
 *
 * The compiler already enforces that a call site *passes* a date, since `at` is
 * required. What it cannot enforce is that the component actually shows it, or
 * that a missing date is admitted rather than hidden — which is what these
 * cover.
 */
describe('VerificationBadgeChip', () => {
  it('shows the date the level rests on', () => {
    const { container } = renderWithProviders(
      <VerificationBadgeChip level="kyc" at="2026-06-30T00:00:00Z" />,
    )
    const text = container.textContent ?? ''
    expect(text).toContain(new Date('2026-06-30T00:00:00Z').toLocaleDateString('en'))
  })

  it('admits when it has no date instead of rendering a clean badge', () => {
    const { getByTestId } = renderWithProviders(
      <VerificationBadgeChip level="peer" at={null} />,
    )
    // Reads worse than a date, which is correct: it is worse. A bare badge here
    // would be the exact overstatement this task exists to remove.
    expect(getByTestId('badge-date').textContent).toContain('date unknown')
  })

  it('renders nothing at all without a level', () => {
    const { container } = renderWithProviders(
      <VerificationBadgeChip level={null} at="2026-06-30T00:00:00Z" />,
    )
    expect(container.textContent).toBe('')
  })
})
