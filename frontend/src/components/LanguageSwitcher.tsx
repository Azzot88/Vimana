import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { updateMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'

const LANGS: { code: string; endonym: string }[] = [
  { code: 'en', endonym: 'English' },
  { code: 'ua', endonym: 'Українська' },
  { code: 'ru', endonym: 'Русский' },
  { code: 'pl', endonym: 'Polski' },
  { code: 'fr', endonym: 'Français' },
  { code: 'es', endonym: 'Español' },
]

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const current = LANGS.find((l) => l.code === i18n.language) ?? LANGS[0]

  /**
   * T3.33 — the account's letters follow the interface.
   *
   * The alternative was a second selector in the profile, asked separately.
   * Two controls for one question is how they come to disagree, and the
   * disagreement is invisible: the screen is in Polish and the letters keep
   * arriving in English, with nothing on either to explain it. Somebody who has
   * just said which language they read has answered the question.
   *
   * Only for a signed-in visitor, and silently: a stranger on the landing page
   * has no account to write to, and a failed write must not stop the interface
   * from changing — the language they see is the part they asked for.
   */
  const pick = (code: string) => {
    i18n.changeLanguage(code)
    localStorage.setItem('lang', code)
    setOpen(false)

    const { user, token, setAuth } = useAuthStore.getState()
    if (!user || !token || user.locale === code) return
    updateMe({ locale: code })
      .then(({ data }) => setAuth(data, token))
      .catch(() => {})
  }

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-body px-2 py-1.5 rounded text-navy/70 hover:text-navy border border-transparent hover:border-navy/10 transition-colors flex items-center gap-1"
      >
        <span>{current.endonym}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <ul className="absolute right-0 mt-1 z-20 bg-white border border-navy/15 rounded-field shadow-md min-w-[9rem] py-1">
          {LANGS.map((l) => (
            <li key={l.code}>
              <button
                type="button"
                onClick={() => pick(l.code)}
                className={`w-full text-left px-3 py-2 text-sm font-body transition-colors ${
                  i18n.language === l.code
                    ? 'text-cyan font-medium bg-cyan/5'
                    : 'text-navy/70 hover:bg-ivory'
                }`}
              >
                {l.endonym}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
