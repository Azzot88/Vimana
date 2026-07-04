import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/react'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { renderWithProviders } from './render'
import i18n from '../i18n'

describe('LanguageSwitcher', () => {
  it('opens dropdown with 6 endonym-named languages', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LanguageSwitcher />)

    await user.click(screen.getByRole('button'))
    expect(screen.getByText('English')).toBeInTheDocument()
    expect(screen.getByText('Українська')).toBeInTheDocument()
    expect(screen.getByText('Русский')).toBeInTheDocument()
    expect(screen.getByText('Polski')).toBeInTheDocument()
    expect(screen.getByText('Français')).toBeInTheDocument()
    expect(screen.getByText('Español')).toBeInTheDocument()
  })

  it('changes i18n language and persists to localStorage on click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LanguageSwitcher />)

    await user.click(screen.getByRole('button'))
    await user.click(screen.getByText('Русский'))

    expect(i18n.language).toBe('ru')
    expect(localStorage.getItem('lang')).toBe('ru')

    await i18n.changeLanguage('en')
  })
})
