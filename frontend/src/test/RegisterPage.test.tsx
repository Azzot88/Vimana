import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import RegisterPage from '../pages/RegisterPage'
import { renderWithProviders } from './render'

describe('RegisterPage', () => {
  it('renders name, email, password inputs (no phone)', () => {
    renderWithProviders(<RegisterPage />)
    expect(screen.getAllByText(/Vimana/i).length).toBeGreaterThan(0)
    const inputs = screen.getAllByRole('textbox')
    expect(inputs.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByPlaceholderText(/••••••••/)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/\+1/)).toBeNull()
  })

  it('shows carrier checkbox', () => {
    renderWithProviders(<RegisterPage />)
    expect(screen.getByRole('checkbox')).toBeInTheDocument()
  })
})
