import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import StatusBadge from '../components/StatusBadge'
import { renderWithProviders } from './render'
import i18n from '../i18n'

describe('StatusBadge', () => {
  it('renders translated status label', () => {
    renderWithProviders(<StatusBadge status="accepted" />)
    const en = i18n.getFixedT('en')
    expect(screen.getByText(en('deals.status.accepted') as string)).toBeInTheDocument()
  })
})
