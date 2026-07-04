import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen, within } from '@testing-library/react'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { renderWithProviders } from './render'
import i18n from '../i18n'

describe('LanguageSwitcher', () => {
  it('opens dropdown with 6 endonym-named languages', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LanguageSwitcher />)

    await user.click(screen.getByRole('button'))
    const list = screen.getByRole('list')
    expect(within(list).getByText('English')).toBeInTheDocument()
    expect(within(list).getByText('Українська')).toBeInTheDocument()
    expect(within(list).getByText('Русский')).toBeInTheDocument()
    expect(within(list).getByText('Polski')).toBeInTheDocument()
    expect(within(list).getByText('Français')).toBeInTheDocument()
    expect(within(list).getByText('Español')).toBeInTheDocument()
  })

  it('changes i18n language and persists to localStorage on click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LanguageSwitcher />)

    await user.click(screen.getByRole('button'))
    const list = screen.getByRole('list')
    await user.click(within(list).getByText('Русский'))

    expect(i18n.language).toBe('ru')
    expect(localStorage.getItem('lang')).toBe('ru')

    await i18n.changeLanguage('en')
  })
})
