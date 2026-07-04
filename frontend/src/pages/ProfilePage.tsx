import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { parsePhoneNumberFromString, getCountryCallingCode } from 'libphonenumber-js/min'
import type { CountryCode } from 'libphonenumber-js/min'
import { useAuthStore } from '../stores/auth'
import { me, updateMe, getTelegramLink } from '../api/auth'
import { listConnections, type Connection } from '../api/social'
import CountryCodeSelect from '../components/CountryCodeSelect'
import MonoText from '../components/MonoText'
import { APP_VERSION } from '../version'

export default function ProfilePage() {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const { user, token, setAuth, logout } = useAuthStore()
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        if (!user && token) {
          const { data } = await me()
          setAuth(data, token)
        }
        const { data } = await listConnections()
        setConnections(data)
      } catch {
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const handleToggle = async (field: 'notify_email' | 'notify_telegram' | 'notify_whatsapp') => {
    if (!user) return
    const newVal = !user[field]
    try {
      const { data } = await updateMe({ [field]: newVal })
      setAuth(data, token!)
    } catch { /* silent */ }
  }

  const handleConnectTelegram = async () => {
    try {
      const { data } = await getTelegramLink()
      window.open(data.link, '_blank')
    } catch { /* silent */ }
  }

  const parsedPhone = useMemo(() => {
    if (!user?.phone) return { iso: '' as CountryCode | '', national: '' }
    const parsed = parsePhoneNumberFromString(user.phone)
    return {
      iso: (parsed?.country ?? '') as CountryCode | '',
      national: parsed?.nationalNumber ?? user.phone.replace(/^\+\d+/, ''),
    }
  }, [user?.phone])

  const [phoneIso, setPhoneIso] = useState<CountryCode | ''>(parsedPhone.iso)
  const [phoneNational, setPhoneNational] = useState<string>(parsedPhone.national)
  const [phoneSaving, setPhoneSaving] = useState(false)

  useEffect(() => {
    setPhoneIso(parsedPhone.iso)
    setPhoneNational(parsedPhone.national)
  }, [parsedPhone.iso, parsedPhone.national])

  const handleSavePhone = async () => {
    if (!phoneIso || !phoneNational) return
    setPhoneSaving(true)
    try {
      const dial = getCountryCallingCode(phoneIso)
      const composed = `+${dial}${phoneNational.replace(/\D/g, '')}`
      const { data } = await updateMe({ phone: composed })
      setAuth(data, token!)
    } catch { /* silent */ }
    finally { setPhoneSaving(false) }
  }

  return (
    <div className="max-w-lg space-y-6">
      <h1 className="font-display font-bold text-2xl text-navy">{t('profile.title')}</h1>

      <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-full bg-navy flex items-center justify-center">
            <span className="text-ivory font-display font-bold text-lg">
              {user?.display_name?.[0]?.toUpperCase() ?? '?'}
            </span>
          </div>
          <div>
            <p className="font-display font-semibold text-lg text-navy">{user?.display_name}</p>
            <p className="text-xs font-mono text-navy/40">
              {user?.is_carrier ? t('dashboard.carrier') : t('dashboard.sender')}
            </p>
          </div>
        </div>
        <div className="pt-2 border-t border-navy/10 space-y-3">
          {user?.email && (
            <div>
              <p className="text-xs font-body font-medium text-navy/40 mb-0.5">{t('profile.email')}</p>
              <MonoText className="text-sm text-navy break-all">{user.email}</MonoText>
            </div>
          )}
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">{t('auth.phone')}</p>
            <div className="flex flex-col sm:flex-row gap-2 sm:items-start">
              <CountryCodeSelect value={phoneIso} onChange={setPhoneIso} />
              <input
                type="tel"
                inputMode="numeric"
                value={phoneNational}
                onChange={(e) => setPhoneNational(e.target.value)}
                placeholder="555 000 0000"
                className="flex-1 border border-navy/20 rounded-lg px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
              />
              <button
                type="button"
                onClick={handleSavePhone}
                disabled={phoneSaving || !phoneIso || !phoneNational}
                className="bg-navy text-ivory font-display font-medium px-4 py-3 min-h-[2.75rem] rounded-lg text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
              >
                {phoneSaving ? t('common.sending') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-navy/10 p-6">
        <p className="text-xs font-body font-medium text-navy/40 mb-1 uppercase tracking-wider">{t('profile.level')}</p>
        <div className="flex items-baseline gap-2 mt-2">
          <MonoText className="text-3xl font-medium text-navy">—</MonoText>
          <span className="text-xs font-body text-navy/40">{t('profile.levelPhase')}</span>
        </div>
        <p className="text-xs font-body text-navy/30 mt-2">{t('profile.levelNote')}</p>
      </div>

      <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display font-semibold text-base text-navy">{t('profile.contacts')}</h2>
          <Link to="/invite" className="text-xs font-body text-cyan hover:underline">
            {t('profile.invite')}
          </Link>
        </div>
        {loading ? (
          <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
        ) : connections.length === 0 ? (
          <p className="text-sm font-body text-navy/40">{t('profile.noContacts')}</p>
        ) : (
          <div className="space-y-2">
            {connections.map((conn) => (
              <div key={conn.id} className="flex items-center justify-between py-2 border-b border-navy/5 last:border-0">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-ivory border border-navy/10 flex items-center justify-center">
                    <span className="text-xs font-display font-bold text-navy">
                      {conn.display_name[0]?.toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-body text-navy">{conn.display_name}</p>
                    <p className="text-xs font-mono text-navy/40">
                      {conn.is_carrier ? t('dashboard.carrier') : t('dashboard.sender')}
                    </p>
                  </div>
                </div>
                <MonoText className="text-xs text-navy/30">
                  {new Date(conn.connected_at).toLocaleDateString(i18n.language)}
                </MonoText>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
        <h2 className="font-display font-semibold text-base text-navy">{t('profile.notifications')}</h2>

        {([
          { key: 'notify_email' as const, label: t('profile.email'), sub: user?.email ?? '—' },
          {
            key: 'notify_telegram' as const,
            label: t('profile.telegram'),
            sub: user?.telegram_chat_id ? t('profile.telegramConnected') : t('profile.telegramNotConnected'),
          },
          {
            key: 'notify_whatsapp' as const,
            label: t('profile.whatsapp'),
            sub: user?.whatsapp_number ?? t('profile.whatsappNotSet'),
          },
        ]).map(({ key, label, sub }) => (
          <div key={key} className="flex items-center justify-between">
            <div>
              <p className="text-sm font-body text-navy">{label}</p>
              <p className="text-xs font-mono text-navy/40">{sub}</p>
            </div>
            <button
              onClick={() => handleToggle(key)}
              className={`w-10 h-6 rounded-full transition-colors ${user?.[key] ? 'bg-cyan' : 'bg-navy/20'}`}
            >
              <span className={`block w-4 h-4 bg-white rounded-full mx-auto transition-transform ${user?.[key] ? 'translate-x-2' : '-translate-x-2'}`} />
            </button>
          </div>
        ))}

        {user?.notify_telegram && !user?.telegram_chat_id && (
          <button
            onClick={handleConnectTelegram}
            className="w-full text-sm font-body text-cyan border border-cyan/30 rounded-lg py-2 hover:bg-cyan/5 transition-colors"
          >
            {t('profile.connectTelegram')}
          </button>
        )}
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={handleLogout}
          className="text-sm font-body text-navy/40 hover:text-navy transition-colors"
        >
          {t('profile.logout')}
        </button>
        <MonoText className="text-xs text-navy/20">v{APP_VERSION}</MonoText>
      </div>
    </div>
  )
}
