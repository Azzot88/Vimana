import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import PhotoPicker from '../components/PhotoPicker'
import { renderWithProviders } from './render'

/**
 * T_UX.28 п.4 (owner, 2026-09-19): «Можно прикреплять несколько фото сразу.
 * Нужен красивый выбор нескольких фото.»
 *
 * What is pinned here is the behaviour the bare file input got wrong: picking
 * again must **add** rather than replace, because photographs of a parcel are
 * taken one at a time and often come from two places in the gallery; and each
 * one has to be removable on its own, because the wrong picture in a piece of
 * evidence cannot be fixed by starting over.
 */
const file = (name: string) =>
  new File(['x'], name, { type: 'image/png', lastModified: 1 })

const picker = (value: File[], onChange = vi.fn()) => {
  renderWithProviders(
    <PhotoPicker value={value} onChange={onChange} label="Фото передачи" />,
  )
  return onChange
}

describe('the photo picker', () => {
  it('adds to what was chosen instead of replacing it', () => {
    const onChange = picker([file('one.png')])
    fireEvent.change(screen.getByTestId('photo-input'), {
      target: { files: [file('two.png')] },
    })
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ name: 'one.png' }),
      expect.objectContaining({ name: 'two.png' }),
    ])
  })

  it('ignores the same photograph chosen twice', () => {
    // People press once, see nothing happen, and press again on the same file.
    const onChange = picker([file('one.png')])
    fireEvent.change(screen.getByTestId('photo-input'), {
      target: { files: [file('one.png')] },
    })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('removes one picture without touching the rest', () => {
    const onChange = picker([file('one.png'), file('two.png')])
    fireEvent.click(screen.getByRole('button', { name: /one\.png/ }))
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ name: 'two.png' }),
    ])
  })

  it('says how many there are, which is the question at a handover', () => {
    picker([file('one.png'), file('two.png')])
    expect(screen.getByText(/2/)).toBeInTheDocument()
  })

  it('offers to add more once something is chosen', () => {
    picker([file('one.png')])
    expect(
      screen.getByRole('button', { name: /add more|Добавить ещё/i }),
    ).toBeInTheDocument()
  })
})
