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
    expect(screen.getByText(/^v0\.01\./)).toBeInTheDocument()
  })
})
