import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router-dom'

/**
 * T_UX.11 — the thing that was missing when a screen went white.
 *
 * Until now a single throw during render unmounted the whole tree and left an
 * empty page with nothing on it: no message, no console breadcrumb the owner
 * would think to look for, no way back except typing a URL. Worse, the symptom
 * was identical for causes that have nothing to do with each other — a
 * `<Route>` that silently failed to land (T3.3, two commits of detective work),
 * a field read off `null`, and a `lazy()` chunk that 404s after a deploy.
 *
 * So this does two jobs, and the split is the point:
 *
 * - **A stale chunk is not a bug.** After a deploy the hashed filenames change;
 *   a tab opened beforehand asks for a file that no longer exists. Nothing is
 *   broken except the page's idea of what to fetch, and a reload fixes it. That
 *   case gets its own text and reloads itself once — silently, because asking
 *   someone to press a button to recover from our deploy is asking them to do
 *   our bookkeeping.
 * - **Anything else is a bug**, and says so plainly, keeps the navigation
 *   working, and shows the message. Not for the visitor's benefit — for the
 *   report they will paste to us.
 *
 * The one-shot guard matters more than it looks. If the chunk is genuinely gone
 * — a half-finished deploy, a bad cache header — reloading on every failure is
 * an infinite refresh loop, which is a worse failure than the white screen it
 * replaces. `sessionStorage` remembers that we already tried; the second time
 * the person gets a button and an explanation instead.
 */

/** Vite/browsers word this differently per engine, and the name is not always
 *  `ChunkLoadError`. Matching on the message is ugly and is the only thing that
 *  works across Chrome, Safari and Firefox. */
const CHUNK_PATTERNS = [
  'failed to fetch dynamically imported module',
  'error loading dynamically imported module',
  'importing a module script failed',
  'failed to load module script',
]

export function isChunkLoadError(error: unknown): boolean {
  const err = error as { name?: string; message?: string } | null
  if (!err) return false
  if (err.name === 'ChunkLoadError') return true
  const message = (err.message ?? '').toLowerCase()
  return CHUNK_PATTERNS.some((p) => message.includes(p))
}

const RELOAD_KEY = 'boundary:chunk-reloaded'

/** Indirection so a test can observe the reload. `window.location` is not
 *  reliably redefinable in jsdom, and a component that cannot be tested for the
 *  one behaviour that risks an infinite loop is not worth the loop. */
export const pageReload = {
  now: () => window.location.reload(),
}

interface Props {
  children: ReactNode
  /** Changing this remounts the boundary — used to clear the error on navigation. */
  resetKey?: string
}

interface State {
  error: Error | null
  staleChunk: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, staleChunk: false }

  static getDerivedStateFromError(error: Error): State {
    return { error, staleChunk: isChunkLoadError(error) }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept deliberately: the console is where this gets diagnosed, and the
    // component stack names the file in one line.
    console.error('Render failed:', error, info.componentStack)

    if (isChunkLoadError(error) && !sessionStorage.getItem(RELOAD_KEY)) {
      sessionStorage.setItem(RELOAD_KEY, '1')
      pageReload.now()
    }
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null, staleChunk: false })
    }
  }

  render() {
    if (!this.state.error) return this.props.children
    return <Fallback error={this.state.error} staleChunk={this.state.staleChunk} />
  }
}

function Fallback({ error, staleChunk }: { error: Error; staleChunk: boolean }) {
  const { t } = useTranslation()
  const reload = () => {
    sessionStorage.removeItem(RELOAD_KEY)
    pageReload.now()
  }

  return (
    <div
      role="alert"
      className="min-h-[60vh] flex items-center justify-center px-4"
      data-testid="error-boundary"
    >
      <div className="w-full max-w-md bg-white rounded-card border border-navy/10 p-6 space-y-3">
        <h1 className="font-display font-bold text-xl text-navy">
          {t(staleChunk ? 'error.staleTitle' : 'error.title')}
        </h1>
        <p className="text-sm font-body text-muted leading-relaxed">
          {t(staleChunk ? 'error.staleBody' : 'error.body')}
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={reload}
            className="px-4 py-2 rounded-field bg-navy text-white text-sm font-body font-medium"
          >
            {t('error.reload')}
          </button>
          <a
            href="/"
            className="px-4 py-2 rounded-field border border-navy/15 text-navy text-sm font-body"
          >
            {t('error.home')}
          </a>
        </div>
        {!staleChunk && (
          // Shown, not hidden behind a support address: the person who hits
          // this is usually the one who can fix it, and a message they can copy
          // is worth more than a reassurance they cannot act on.
          <details className="pt-1">
            <summary className="text-xs font-body text-muted cursor-pointer">
              {t('error.details')}
            </summary>
            <pre className="mt-2 text-[11px] font-mono text-navy whitespace-pre-wrap break-words">
              {error.message || String(error)}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}

/**
 * Route-scoped wrapper. The key is the path, so navigating away from a broken
 * screen clears the error — without it the boundary would latch, and the first
 * failure would make the rest of the session look broken too.
 *
 * Called by: `App`.
 */
export default function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation()
  return <ErrorBoundary resetKey={location.pathname}>{children}</ErrorBoundary>
}
