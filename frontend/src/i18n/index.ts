import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import ua from './locales/ua.json'
import ru from './locales/ru.json'
import pl from './locales/pl.json'
import fr from './locales/fr.json'
import es from './locales/es.json'

const LEGACY_LANG_MAP: Record<string, string> = { uk: 'ua' }

const rawSaved = localStorage.getItem('lang') ?? 'en'
const savedLang = LEGACY_LANG_MAP[rawSaved] ?? rawSaved
if (savedLang !== rawSaved) {
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
