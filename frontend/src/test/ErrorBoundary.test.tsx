import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { ErrorBoundary, isChunkLoadError, pageReload } from '../components/ErrorBoundary'
import { renderWithProviders } from './render'

function Boom({ error }: { error: Error }): never {
  throw error
}

const chunkError = () =>
  new Error('Failed to fetch dynamically imported module: /assets/DashboardPage-a1b2.js')

describe('isChunkLoadError', () => {
  it('recognises the wording of each engine', () => {
    for (const message of [
      'Failed to fetch dynamically imported module: /assets/x.js',
      'error loading dynamically imported module',
      'Importing a module script failed.',
      'Failed to load module script',
    ]) {
      expect(isChunkLoadError(new Error(message))).toBe(true)
    }
  })

  it('recognises the older named error', () => {
    const err = new Error('boom')
    err.name = 'ChunkLoadError'
    expect(isChunkLoadError(err)).toBe(true)
  })

  it('does not mistake an ordinary bug for a stale deploy', () => {
    expect(isChunkLoadError(new TypeError("Cannot read properties of null"))).toBe(false)
    expect(isChunkLoadError(null)).toBe(false)
  })
})

describe('ErrorBoundary', () => {
  let consoleError: ReturnType<typeof vi.spyOn>
  let reload: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    // React logs the caught error itself; the test output is not the place to
    // re-read it, and a failing assertion is louder than a stack trace.
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    reload = vi.spyOn(pageReload, 'now').mockImplementation(() => {})
    sessionStorage.clear()
  })

  afterEach(() => {
    consoleError.mockRestore()
    reload.mockRestore()
  })

  it('renders children when nothing throws', () => {
    renderWithProviders(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('all good')).toBeInTheDocument()
    expect(screen.queryByTestId('error-boundary')).not.toBeInTheDocument()
  })

  it('shows a message instead of a white screen', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Boom error={new TypeError('nope')} />
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('error-boundary')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('shows the message so it can be pasted into a report', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Boom error={new TypeError('cannot read x of null')} />
      </ErrorBoundary>,
    )
    expect(screen.getByText(/cannot read x of null/)).toBeInTheDocument()
  })

  it('reloads once on a stale chunk — a deploy is not the visitor’s problem', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Boom error={chunkError()} />
      </ErrorBoundary>,
    )
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('does not reload a second time — a loop is worse than the white screen', () => {
    sessionStorage.setItem('boundary:chunk-reloaded', '1')
    renderWithProviders(
      <ErrorBoundary>
        <Boom error={chunkError()} />
      </ErrorBoundary>,
    )
    expect(reload).not.toHaveBeenCalled()
    expect(screen.getByTestId('error-boundary')).toBeInTheDocument()
  })

  it('does not reload for an ordinary bug', () => {
    renderWithProviders(
      <ErrorBoundary>
        <Boom error={new TypeError('nope')} />
      </ErrorBoundary>,
    )
    expect(reload).not.toHaveBeenCalled()
  })

  it('offers no technical details for a stale chunk — there is nothing to report', () => {
    sessionStorage.setItem('boundary:chunk-reloaded', '1')
    renderWithProviders(
      <ErrorBoundary>
        <Boom error={chunkError()} />
      </ErrorBoundary>,
    )
    expect(screen.queryByText(/Failed to fetch dynamically/)).not.toBeInTheDocument()
  })

  it('clears the error when the reset key changes', () => {
    const { rerender } = renderWithProviders(
      <ErrorBoundary resetKey="/a">
        <Boom error={new TypeError('nope')} />
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('error-boundary')).toBeInTheDocument()

    // Navigating away must not leave the rest of the session looking broken.
    rerender(
      <ErrorBoundary resetKey="/b">
        <p>recovered</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('recovered')).toBeInTheDocument()
    expect(screen.queryByTestId('error-boundary')).not.toBeInTheDocument()
  })
})
