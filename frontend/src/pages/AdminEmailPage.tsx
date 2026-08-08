import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  getEmailTemplates,
  getMailStatus,
  sendTestEmail,
  type EmailTemplate,
  type MailCircuit,
  type MailStatus,
} from '../api/admin'
import { useAuthStore } from '../stores/auth'
import MonoText from '../components/MonoText'

const LOCALE_NAMES: Record<string, string> = {
  en: 'English',
  ru: 'Русский',
  ua: 'Українська',
  pl: 'Polski',
  fr: 'Français',
  es: 'Español',
}

/**
 * T_UX.9 pt.2 — the mail console.
 *
 * Two things live here and they are deliberately kept apart on screen, because
 * they are kept apart in the backend: what the letters *look like* (pure
 * rendering, no SMTP anywhere in the path) and what the two circuits are
 * *pointed at* (read-only, plus one test send that is hard-wired to the
 * preview circuit).
 *
 * The letters render inside iframes. An email is a full HTML document with its
 * own table layout and inline styles; dropping that into the page would let it
 * inherit Tailwind's reset and show something the recipient will never see —
 * a preview that lies is worse than no preview.
 */
function CircuitCard({
  title,
  hint,
  circuit,
  tone,
}: {
  title: string
  hint: string
  circuit: MailCircuit
  tone: 'live' | 'preview'
}) {
  const { t } = useTranslation()
  const accent = tone === 'live' ? 'border-amber/40 bg-amber/5' : 'border-cyan/40 bg-cyan/5'
  return (
    <div className={`rounded-field border p-4 space-y-2 ${accent}`}>
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-display font-medium text-sm text-navy">{title}</p>
        <MonoText
          className={`text-[11px] ${circuit.configured ? 'text-success' : 'text-muted'}`}
        >
          {circuit.configured ? t('adminEmail.on') : t('adminEmail.off')}
        </MonoText>
      </div>
      <p className="text-[11px] font-body text-muted leading-snug">{hint}</p>
      {circuit.configured && (
        <dl className="space-y-0.5 pt-1">
          {(
            [
              [t('adminEmail.host'), `${circuit.host}:${circuit.port}`],
              [t('adminEmail.user'), circuit.user],
              [t('adminEmail.tls'), circuit.tls],
            ] as const
          ).map(([label, value]) => (
            <div key={label} className="flex gap-2 text-xs">
              <dt className="text-muted min-w-[68px]">{label}</dt>
              <dd>
                <MonoText className="text-xs text-navy break-all">{value}</MonoText>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

export default function AdminEmailPage() {
  const { t, i18n } = useTranslation()
  const { user } = useAuthStore()

  const [status, setStatus] = useState<MailStatus | null>(null)
  const [letters, setLetters] = useState<EmailTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // The preview language is its own piece of state, seeded from the interface
  // language and never written back to it. Switching it must not move the
  // ground under the person reading — they are inspecting letters, not
  // changing their own settings.
  const [previewLocale, setPreviewLocale] = useState<string>(
    () => (i18n.language || 'en').split('-')[0],
  )
  const [showText, setShowText] = useState(false)

  const [testTo, setTestTo] = useState('')
  const [testResult, setTestResult] = useState('')
  const [sending, setSending] = useState(false)

  const isSuper = user?.role === 'superuser'

  useEffect(() => {
    if (!isSuper) return
    getMailStatus()
      .then(({ data }) => setStatus(data))
      .catch(() => setError(t('adminEmail.errorStatus')))
  }, [isSuper, t])

  useEffect(() => {
    if (!isSuper) return
    setLoading(true)
    getEmailTemplates(previewLocale)
      .then(({ data }) => setLetters(data.letters))
      .catch(() => setError(t('adminEmail.errorTemplates')))
      .finally(() => setLoading(false))
  }, [isSuper, previewLocale, t])

  const locales = useMemo(() => status?.locales ?? ['en'], [status])

  const handleTest = async () => {
    setSending(true)
    setTestResult('')
    try {
      const { data } = await sendTestEmail(testTo, 'verification_code', previewLocale)
      setTestResult(
        data.delivered ? t('adminEmail.testSent') : t('adminEmail.testNotSent'),
      )
    } catch (err: unknown) {
      const s = (err as { response?: { status?: number } })?.response?.status
      setTestResult(s === 503 ? t('adminEmail.testNoCircuit') : t('adminEmail.testError'))
    } finally {
      setSending(false)
    }
  }

  if (!isSuper) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10">
        <p className="font-body text-sm text-muted">{t('adminEmail.forbidden')}</p>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display font-bold text-2xl text-navy">
            {t('adminEmail.title')}
          </h1>
          <p className="text-sm font-body text-muted mt-1 max-w-xl">
            {t('adminEmail.subtitle')}
          </p>
        </div>
        <Link to="/profile" className="text-sm font-body text-link hover:underline">
          {t('adminEmail.back')}
        </Link>
      </div>

      {error && (
        <p className="rounded-field border border-danger/30 bg-danger/5 p-3 text-sm font-body text-danger">
          {error}
        </p>
      )}

      {/* ── circuits ─────────────────────────────────────────────────────── */}
      {status && (
        <section className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
          <div>
            <h2 className="font-display font-semibold text-base text-navy">
              {t('adminEmail.circuitsTitle')}
            </h2>
            <p className="text-xs font-body text-muted mt-0.5">
              {t('adminEmail.circuitsHint')}
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <CircuitCard
              title={t('adminEmail.liveTitle')}
              hint={t('adminEmail.liveHint')}
              circuit={status.live}
              tone="live"
            />
            <CircuitCard
              title={t('adminEmail.previewTitle')}
              hint={t('adminEmail.previewHint')}
              circuit={status.preview}
              tone="preview"
            />
          </div>

          <div className="rounded-field border border-navy/10 p-4 space-y-2">
            <p className="font-display font-medium text-sm text-navy">
              {t('adminEmail.testTitle')}
            </p>
            <p className="text-[11px] font-body text-muted leading-snug">
              {t('adminEmail.testHint')}
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <label className="sr-only" htmlFor="mail-test-to">
                {t('adminEmail.testTo')}
              </label>
              <input
                id="mail-test-to"
                type="email"
                value={testTo}
                onChange={(e) => setTestTo(e.target.value)}
                placeholder="someone@example.test"
                className="flex-1 min-w-[220px] border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
              />
              <button
                type="button"
                onClick={handleTest}
                disabled={!testTo || sending || !status.preview.configured}
                className="px-4 py-2 rounded-field bg-navy text-white text-sm font-body font-medium disabled:opacity-40"
              >
                {sending ? t('adminEmail.testSending') : t('adminEmail.testSend')}
              </button>
            </div>
            {testResult && (
              <MonoText className="text-[11px] text-navy">{testResult}</MonoText>
            )}
          </div>
        </section>
      )}

      {/* ── letters ──────────────────────────────────────────────────────── */}
      <section className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="font-display font-semibold text-base text-navy">
              {t('adminEmail.lettersTitle')}
            </h2>
            <p className="text-xs font-body text-muted mt-0.5 max-w-lg">
              {t('adminEmail.lettersHint')}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowText((v) => !v)}
            className="text-xs font-body text-link hover:underline"
          >
            {showText ? t('adminEmail.showHtml') : t('adminEmail.showText')}
          </button>
        </div>

        {/* The language switch for the letters only. Says so out loud, because
            a language control at the top of a page is read as the site's. */}
        <div className="rounded-field border border-navy/10 bg-ivory p-3 space-y-2">
          <p className="text-[11px] font-body text-muted">
            {t('adminEmail.localeHint')}
          </p>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('adminEmail.localeGroup')}>
            {locales.map((loc) => (
              <button
                key={loc}
                type="button"
                onClick={() => setPreviewLocale(loc)}
                aria-pressed={previewLocale === loc}
                className={`px-3 py-1.5 rounded-field text-xs font-body border transition-colors ${
                  previewLocale === loc
                    ? 'bg-navy text-white border-navy'
                    : 'bg-white text-navy border-navy/15 hover:border-cyan'
                }`}
              >
                {LOCALE_NAMES[loc] ?? loc}
              </button>
            ))}
          </div>
        </div>

        {loading && (
          <p className="font-body text-sm text-muted">{t('adminEmail.loading')}</p>
        )}

        <div className="space-y-8">
          {letters.map((letter) => (
            <article key={letter.kind} className="space-y-2">
              <div className="flex items-baseline justify-between gap-3 flex-wrap">
                <MonoText className="text-[11px] uppercase tracking-[0.14em] text-muted">
                  {letter.kind}
                </MonoText>
                <MonoText className="text-[11px] text-muted">{previewLocale}</MonoText>
              </div>
              <p className="font-display font-medium text-sm text-navy">
                {letter.subject}
              </p>
              {showText ? (
                <pre className="rounded-field border border-navy/10 bg-ivory p-4 text-xs font-mono text-navy whitespace-pre-wrap overflow-x-auto">
                  {letter.text}
                </pre>
              ) : (
                <iframe
                  // `sandbox` with nothing enabled: a letter is inert content
                  // here, and the console must not become a way to run whatever
                  // a template happens to contain.
                  sandbox=""
                  title={`${letter.kind} · ${previewLocale}`}
                  srcDoc={letter.html}
                  className="w-full h-[560px] rounded-field border border-navy/10 bg-white"
                />
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
