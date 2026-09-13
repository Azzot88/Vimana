import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import CategorySelect from '../components/CategorySelect'
import { renderWithProviders } from './render'

/**
 * T3.11.27 — «Отправить посылку: должно быть больше категорий, все категории»
 * and «Если не выбрать категорию заявка не создаётся» (owner, 2026-09-12).
 *
 * A request is a **pick**, never an invention: the master rule from 2026-09-08
 * is «в заявке появляется только то что есть в опубликованом рейсе». With no
 * list on the trip that means the whole catalogue — not a blank search box,
 * which asks a sender to guess words and lets them name a category the carrier
 * never agreed to carry.
 */
vi.mock('../api/categories', async () => {
  const actual =
    await vi.importActual<typeof import('../api/categories')>('../api/categories')
  return { ...actual, listCategories: vi.fn() }
})

import { listCategories } from '../api/categories'

const cat = (name_key: string, sort_order = 0) => ({
  name_key,
  is_default: true,
  usage_count: 0,
  sort_order,
})

const CATALOGUE = [
  cat('document', 0),
  cat('clothing', 1),
  cat('electronics', 2),
  cat('animal', 3),
]

beforeEach(() => {
  vi.mocked(listCategories).mockReset().mockResolvedValue({
    data: CATALOGUE,
  } as never)
})

describe('CategorySelect', () => {
  it('draws the whole catalogue when the trip named nothing', async () => {
    renderWithProviders(
      <CategorySelect value="" onChange={() => {}} catalogue />,
    )
    await waitFor(() => expect(screen.getByText(/Documents|Документ/i)).toBeInTheDocument())
    expect(screen.getByText(/Animal|Животн/i)).toBeInTheDocument()
    // No free text: the sender picks from what exists.
    expect(document.querySelector('input[type="text"]')).toBeNull()
  })

  it('keeps the other chips after one is chosen', async () => {
    /* The defect this pins: the list is fetched with the search query, and the
       query follows the chosen value — so picking «Документы» searched for
       «document» and the remaining six categories disappeared behind the one
       already picked. */
    const { rerender } = renderWithProviders(
      <CategorySelect value="" onChange={() => {}} catalogue />,
    )
    await waitFor(() => expect(screen.getByText(/Animal|Животн/i)).toBeInTheDocument())

    rerender(<CategorySelect value="document" onChange={() => {}} catalogue />)
    await waitFor(() =>
      expect(listCategories).toHaveBeenCalledWith(''),
    )
    expect(screen.getByText(/Animal|Животн/i)).toBeInTheDocument()
  })

  it('narrows to what this trip carries when the trip said so', async () => {
    renderWithProviders(
      <CategorySelect
        value=""
        onChange={() => {}}
        catalogue
        only={['document', 'clothing']}
      />,
    )
    expect(screen.getByText(/Documents|Документ/i)).toBeInTheDocument()
    expect(screen.queryByText(/Animal|Животн/i)).not.toBeInTheDocument()
  })

  it('reports the choice by its key, not by its label', async () => {
    // The label is translated; the key is what the server stores and matches
    // against the trip's list.
    const onChange = vi.fn()
    renderWithProviders(
      <CategorySelect value="" onChange={onChange} only={['document']} />,
    )
    fireEvent.click(screen.getByText(/Documents|Документ/i))
    expect(onChange).toHaveBeenCalledWith('document')
  })
})
