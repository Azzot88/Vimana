import { useTranslation } from 'react-i18next'

const LANGS = [
  { code: 'en', label: 'EN' },
  { code: 'uk', label: 'UK' },
  { code: 'pl', label: 'PL' },
  { code: 'fr', label: 'FR' },
  { code: 'es', label: 'ES' },
]

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()

  const change = (code: string) => {
    i18n.changeLanguage(code)
    localStorage.setItem('lang', code)
  }

  return (
    <div className="flex items-center gap-0.5">
      {LANGS.map(({ code, label }) => (
        <button
          key={code}
          onClick={() => change(code)}
          className={`text-xs font-mono px-1.5 py-0.5 rounded transition-colors ${
            i18n.language === code
              ? 'text-cyan font-bold'
              : 'text-navy/30 hover:text-navy/70'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
