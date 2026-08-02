import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { act, screen, waitFor, within } from '@testing-library/react'
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

    // `changeLanguage` resolves after the click handler returns, and the
    // re-render it causes lands outside `act` — which is what the warning in
    // the output was about. Waiting for the settled value puts that update
    // inside `act` and, incidentally, tests the thing that actually matters:
    // the switch completes, not that it started.
    await waitFor(() => expect(i18n.language).toBe('ru'))
    expect(localStorage.getItem('lang')).toBe('ru')

    // The reset is a state update too, so it needs the same treatment or the
    // warning simply moves to the end of the test.
    await act(async () => {
      await i18n.changeLanguage('en')
    })
  })
})
