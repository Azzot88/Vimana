import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import LoginPage from '../pages/LoginPage'
import { renderWithProviders } from './render'

describe('LoginPage', () => {
  it('renders title, subtitle, and both inputs', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getAllByText(/Vimana/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Sacred Logistics/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/user@example.com/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/••••••••/)).toBeInTheDocument()
  })

  it('shows Sign up link to /register', () => {
    renderWithProviders(<LoginPage />)
    const link = screen.getByRole('link', { name: /sign up/i })
    expect(link).toHaveAttribute('href', '/register')
  })

  it('renders version badge', () => {
    renderWithProviders(<LoginPage />)
    // Format `v0.<phase:02>.<task>` — match any phase, not just 0.01.
    expect(screen.getByText(/^v0\.\d{2}\./)).toBeInTheDocument()
  })
})
