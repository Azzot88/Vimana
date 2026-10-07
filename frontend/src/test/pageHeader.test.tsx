import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import PageHeader from '../components/PageHeader'
import { renderWithProviders } from './render'

/**
 * T_UX.40 — the one header every screen in the app shell opens with.
 *
 * Pinned: the title is the page's single `h1`, the way back is a real link to
 * the address given, and the optional parts render only when given — a header
 * that drew an empty description row would put a gap under every title.
 */
describe('PageHeader', () => {
  it('renders every part it is given', () => {
    renderWithProviders(
      <PageHeader
        back={{ to: '/trips', label: 'Back to trips' }}
        eyebrow="Profile"
        title="Vault"
        description="Your files and the vaults of your deals."
        aside={<button type="button">Sort</button>}
      />,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Vault' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← Back to trips' })).toHaveAttribute('href', '/trips')
    expect(screen.getByText('Profile')).toBeInTheDocument()
    expect(screen.getByText('Your files and the vaults of your deals.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sort' })).toBeInTheDocument()
  })

  it('renders the title alone when nothing else is given', () => {
    const { container } = renderWithProviders(<PageHeader title="Trips" />)
    expect(screen.getAllByRole('heading')).toHaveLength(1)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(container.querySelectorAll('header p')).toHaveLength(0)
  })
})
