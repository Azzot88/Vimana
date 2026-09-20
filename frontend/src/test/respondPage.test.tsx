import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import RespondPage from '../pages/RespondPage'
import ProfileCargoTemplatesPage from '../pages/ProfileCargoTemplatesPage'
import { useAuthStore } from '../stores/auth'
import type { User } from '../api/auth'
import type { Trip } from '../api/trips'
import type { CargoTemplate } from '../api/cargoTemplates'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T3.12.03 pt.2 — «Отклики» and the cargo templates behind it.
 *
 * `D-CARGO-MODEL`: a template reaches a cargo as a snapshot. On screen that
 * means the template fills the form and the form is what is sent — so what is
 * pinned is what the press sends, what a template may not fill in (a category
 * this trip does not carry), and who is not offered the form at all.
 */
vi.mock('../api/trips', async () => {
  const actual = await vi.importActual<typeof import('../api/trips')>('../api/trips')
  return { ...actual, getTrip: vi.fn() }
})
vi.mock('../api/cargoTemplates', async () => {
  const actual =
    await vi.importActual<typeof import('../api/cargoTemplates')>('../api/cargoTemplates')
  return {
    ...actual,
    listCargoTemplates: vi.fn(),
    createCargoTemplate: vi.fn(),
    updateCargoTemplate: vi.fn(),
    deleteCargoTemplate: vi.fn(),
  }
})
vi.mock('../api/deals', async () => {
  const actual = await vi.importActual<typeof import('../api/deals')>('../api/deals')
  return { ...actual, matchDeal: vi.fn() }
})
vi.mock('../api/terms', async () => {
  const actual = await vi.importActual<typeof import('../api/terms')>('../api/terms')
  return { ...actual, raiseCardWithFiles: vi.fn() }
})
vi.mock('../api/categories', async () => {
  const actual =
    await vi.importActual<typeof import('../api/categories')>('../api/categories')
  return { ...actual, listCategories: vi.fn() }
})
// The warning asks the server about the corridor; nothing here is about it.
vi.mock('../components/LeadTimeWarning', () => ({ default: () => null }))

import { getTrip } from '../api/trips'
import { deleteCargoTemplate, listCargoTemplates } from '../api/cargoTemplates'
import { matchDeal } from '../api/deals'
import { raiseCardWithFiles } from '../api/terms'
import { listCategories } from '../api/categories'

const t = i18n.t.bind(i18n)

const signIn = (id: string) =>
  useAuthStore.getState().setAuth(
    {
      id,
      display_name: 'Anna',
      handle: null,
      email: 'a@b.test',
      phone: null,
      can_carry: false,
      can_send: true,
      active_mode: 'sender',
      roles: ['user'],
      nostr_pubkey: null,
      business_activity_level: null,
    } as unknown as User,
    'token-1',
  )

const trip = {
  id: 't1',
  carrier_id: 'u-carrier',
  carrier_name: 'Boris',
  origin: 'DXB',
  destination: 'JFK',
  depart_at: '2030-01-10T10:00:00Z',
  segments: [],
  capacity: null,
  allowed_categories: ['document'],
  status: 'open',
  created_at: '2026-09-14T10:00:00Z',
} as unknown as Trip

const template = (over: Partial<CargoTemplate>): CargoTemplate => ({
  id: 'tp',
  name: 'Template',
  category: null,
  declared_value: null,
  description: null,
  weight_kg: null,
  dimensions_cm: null,
  fragile: false,
  open_on_handover: false,
  cargo_url: null,
  created_at: '2026-09-14T10:00:00Z',
  updated_at: '2026-09-14T10:00:00Z',
  ...over,
})

const TEMPLATES = [
  template({
    id: 'tp1',
    name: 'Lisbon papers',
    category: 'document',
    declared_value: 120,
    description: 'a folder',
    weight_kg: 0.4,
    dimensions_cm: [30, 22, 2],
    fragile: true,
  }),
  template({ id: 'tp2', name: 'Medicine', category: 'medicine', description: 'pills' }),
]

const documentChip = () =>
  screen.getByRole('button', {
    name: t('categories.document', { defaultValue: '' }) || 'document',
  })

const renderRespond = () =>
  renderWithProviders(
    <Routes>
      <Route path="/trips/:tripId/respond" element={<RespondPage />} />
    </Routes>,
    { route: '/trips/t1/respond' },
  )

beforeEach(() => {
  signIn('u-sender')
  vi.mocked(getTrip).mockReset().mockResolvedValue({ data: trip } as never)
  vi.mocked(listCargoTemplates).mockReset().mockResolvedValue({ data: TEMPLATES } as never)
  vi.mocked(matchDeal).mockReset().mockResolvedValue({ data: { id: 'd1' } } as never)
  vi.mocked(raiseCardWithFiles).mockReset().mockResolvedValue({} as never)
  vi.mocked(deleteCargoTemplate).mockReset().mockResolvedValue({} as never)
  vi.mocked(listCategories).mockReset().mockResolvedValue({ data: [] } as never)
})

describe('RespondPage', () => {
  it('shows the storage tariff on the trip opened in full', async () => {
    /* T_DEAL.1 (owner, 2026-09-20): «Тариф за хранение должен быть убран из
       описания рейса, которое видно при выборе… видно при открывании рейса в
       полном формате.» This is that full format, and the tariff has to be
       readable **before** the response: storage is paid by the same side that
       pays for the carriage. */
    vi.mocked(getTrip).mockResolvedValue({
      data: {
        ...trip,
        storage_terms: { free_days: 2, price: 1, unit: 'kg', currency: 'USD' },
      },
    } as never)
    renderRespond()

    const line = await screen.findByTestId('trip-storage')
    expect(line).toHaveTextContent('2')
    expect(line).toHaveTextContent('USD')
  })

  it('says nothing about storage when the carrier did not offer it', async () => {
    // Silence is not free storage, and an empty label would read as a field
    // somebody failed to fill rather than a service nobody sells.
    renderRespond()
    await screen.findByRole('button', { name: 'Lisbon papers' })
    expect(screen.queryByTestId('trip-storage')).not.toBeInTheDocument()
  })

  it('fills the form from a template', async () => {
    renderRespond()
    fireEvent.click(await screen.findByRole('button', { name: 'Lisbon papers' }))

    expect(screen.getByLabelText(t('trips.cargoDescription'))).toHaveValue('a folder')
    expect(screen.getByLabelText(t('trips.declaredValue'))).toHaveValue(120)
    expect(screen.getByLabelText(t('terms.weight'))).toHaveValue(0.4)
    expect(screen.getByLabelText(t('cargoFields.length'))).toHaveValue(30)
    expect(screen.getByLabelText(t('agreement.field.fragile'))).toBeChecked()
    expect(documentChip()).toHaveAttribute('aria-pressed', 'true')
  })

  it('leaves unanswered a category this trip does not carry', async () => {
    renderRespond()
    fireEvent.click(await screen.findByRole('button', { name: 'Medicine' }))

    expect(screen.getByLabelText(t('trips.cargoDescription'))).toHaveValue('pills')
    expect(documentChip()).toHaveAttribute('aria-pressed', 'false')

    fireEvent.submit(screen.getByRole('button', { name: t('trips.submit') }).closest('form')!)
    expect(await screen.findByText(t('trips.categoryRequired'))).toBeInTheDocument()
    expect(matchDeal).not.toHaveBeenCalled()
  })

  it('sends the cargo on screen, and a template name only when asked', async () => {
    renderRespond()
    fireEvent.click(await screen.findByRole('button', { name: 'Lisbon papers' }))
    fireEvent.click(screen.getByLabelText(t('respond.saveAsTemplate')))
    fireEvent.change(screen.getByLabelText(t('respond.templateName')), {
      target: { value: '  Papers  ' },
    })
    fireEvent.submit(screen.getByRole('button', { name: t('trips.submit') }).closest('form')!)

    await waitFor(() => expect(matchDeal).toHaveBeenCalledTimes(1))
    expect(matchDeal).toHaveBeenCalledWith({
      trip_id: 't1',
      cargo: {
        category: 'document',
        declared_value: 120,
        description: 'a folder',
        weight_kg: 0.4,
        dimensions_cm: [30, 22, 2],
        fragile: true,
        open_on_handover: false,
        cargo_url: undefined,
      },
      save_as_template: 'Papers',
    })
    // No photographs chosen, so no card.
    expect(raiseCardWithFiles).not.toHaveBeenCalled()
  })

  it('files the chosen photographs into the new deal as one card', async () => {
    renderRespond()
    fireEvent.click(await screen.findByRole('button', { name: 'Lisbon papers' }))
    const one = new File(['a'], 'front.png', { type: 'image/png' })
    const two = new File(['b'], 'back.png', { type: 'image/png' })
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [one, two] },
    })
    fireEvent.submit(screen.getByRole('button', { name: t('trips.submit') }).closest('form')!)

    await waitFor(() =>
      expect(raiseCardWithFiles).toHaveBeenCalledWith('d1', 'cargo.photographed', [one, two]),
    )
  })

  it('says the deal exists when its photographs did not upload', async () => {
    vi.mocked(raiseCardWithFiles).mockRejectedValue(new Error('415'))
    renderRespond()
    fireEvent.click(await screen.findByRole('button', { name: 'Lisbon papers' }))
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(['a'], 'x.png', { type: 'image/png' })] },
    })
    fireEvent.submit(screen.getByRole('button', { name: t('trips.submit') }).closest('form')!)

    expect(await screen.findByText(t('respond.photosFailed'))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t('respond.openDeal') })).toHaveAttribute(
      'href',
      '/deals/d1/vault',
    )
  })

  it('does not offer the carrier a response to their own trip', async () => {
    signIn('u-carrier')
    renderRespond()
    expect(await screen.findByText(t('respond.ownTrip'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t('trips.submit') })).toBeNull()
  })

  it('says so when the trip is gone', async () => {
    vi.mocked(getTrip).mockRejectedValue(new Error('404'))
    renderRespond()
    expect(await screen.findByText(t('respond.tripGone'))).toBeInTheDocument()
  })
})

describe('ProfileCargoTemplatesPage', () => {
  it('lists the templates and deletes one only after confirming', async () => {
    const confirm = vi.spyOn(window, 'confirm')
    renderWithProviders(<ProfileCargoTemplatesPage />)
    expect(await screen.findByText('Lisbon papers')).toBeInTheDocument()
    const [first] = screen.getAllByRole('button', { name: t('cargoTemplates.delete') })

    confirm.mockReturnValueOnce(false)
    fireEvent.click(first)
    expect(deleteCargoTemplate).not.toHaveBeenCalled()

    confirm.mockReturnValueOnce(true)
    fireEvent.click(first)
    await waitFor(() => expect(deleteCargoTemplate).toHaveBeenCalledWith('tp1'))
    confirm.mockRestore()
  })
})
