import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import ua from './locales/ua.json'
import ru from './locales/ru.json'
import pl from './locales/pl.json'
import fr from './locales/fr.json'
import es from './locales/es.json'

const LEGACY_LANG_MAP: Record<string, string> = { uk: 'ua' }

// T_UX.7 pt.2 — this module is imported by the prerender build, which runs in
// Node where `localStorage` does not exist. Reading it unguarded threw at import
// time and took the whole build down before rendering a single element.
const hasStorage = typeof localStorage !== 'undefined'

const rawSaved = (hasStorage && localStorage.getItem('lang')) || 'en'
const savedLang = LEGACY_LANG_MAP[rawSaved] ?? rawSaved
if (hasStorage && savedLang !== rawSaved) {
  localStorage.setItem('lang', savedLang)
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ua: { translation: ua },
    ru: { translation: ru },
    pl: { translation: pl },
    fr: { translation: fr },
    es: { translation: es },
  },
  lng: savedLang,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n
