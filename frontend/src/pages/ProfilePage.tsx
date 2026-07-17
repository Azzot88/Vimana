import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { parsePhoneNumberFromString, getCountryCallingCode } from 'libphonenumber-js/min'
import type { CountryCode } from 'libphonenumber-js/min'
import { useAuthStore } from '../stores/auth'
import { me, updateMe, getTelegramLink, type UserUpdate } from '../api/auth'
import { createInvite, listConnections, listMyInvites, type Connection, type MyInvite } from '../api/social'
import api from '../api/client'
import AddressForm from '../components/AddressForm'
import CountryCodeSelect from '../components/CountryCodeSelect'
import KeypairSection from '../components/KeypairSection'
import MonoText from '../components/MonoText'
import TrustCirclesSection from '../components/TrustCirclesSection'
import VerificationSection from '../components/VerificationSection'
import { APP_VERSION } from '../version'

function formatRemaining(expiresAt: string): string {
  const remainingMs = new Date(expiresAt).getTime() - Date.now()
  if (remainingMs <= 0) return '0д'
  const totalHours = Math.floor(remainingMs / 3_600_000)
  const days = Math.floor(totalHours / 24)
  const hours = totalHours % 24
  if (days === 0) return `${hours}ч`
  return `${days}д ${hours}ч`
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const { user, token, setAuth, logout } = useAuthStore()
  const [connections, setConnections] = useState<Connection[]>([])
  const [invites, setInvites] = useState<MyInvite[]>([])
  const [invitesLoading, setInvitesLoading] = useState(false)
  const [creatingInvite, setCreatingInvite] = useState(false)
  const [loading, setLoading] = useState(true)
  const [countryOptions, setCountryOptions] = useState<Array<{ iso: string; name: string }>>([])
  const [addressSaving, setAddressSaving] = useState(false)
  const [addressSaved, setAddressSaved] = useState(false)

  useEffect(() => {
    let cancelled = false
    const loadCountries = async () => {
      try {
        const { data } = await api.get<Array<{ iso: string; count: number }>>('/api/airports/countries')
        if (cancelled) return
        const display = new Intl.DisplayNames([i18n.language], { type: 'region' })
        const enriched = data
          .map((c) => ({ iso: c.iso, name: display.of(c.iso) || c.iso }))
          .sort((a, b) => a.name.localeCompare(b.name))
        setCountryOptions(enriched)
      } catch {
        // silent
      }
    }
    loadCountries()
    return () => {
      cancelled = true
    }
  }, [i18n.language])

  const handleAddressChange = async (patch: Partial<UserUpdate>) => {
    if (!user) return
    setAuth({ ...user, ...patch } as typeof user, token ?? '')
    setAddressSaving(true)
    setAddressSaved(false)
    try {
      const { data } = await updateMe(patch)
      setAuth(data, token ?? '')
      setAddressSaved(true)
      setTimeout(() => setAddressSaved(false), 1500)
    } catch {
      // silent — user will notice via missing checkmark
    } finally {
      setAddressSaving(false)
    }
  }

  const loadInvites = async () => {
    setInvitesLoading(true)
    try {
      const { data } = await listMyInvites()
      setInvites(data)
    } catch { /* silent */ }
    finally { setInvitesLoading(false) }
  }

  useEffect(() => {
    const load = async () => {
      try {
        if (!user && token) {
          const { data } = await me()
          setAuth(data, token)
        }
        const [conns] = await Promise.all([listConnections(), loadInvites()])
        setConnections(conns.data)
      } catch {
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const handleCreateInvite = async () => {
    setCreatingInvite(true)
    try {
      await createInvite()
      await loadInvites()
    } catch { /* silent */ }
    finally { setCreatingInvite(false) }
  }

  const copyInviteLink = (token: string) => {
    const url = `${window.location.origin}/invite/${token}`
    navigator.clipboard?.writeText(url).catch(() => {})
  }

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
              {user?.active_mode === 'carrier' ? t('dashboard.carrier') : t('dashboard.sender')}
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
        <div className="flex items-center justify-between">
          <h2 className="font-display font-semibold text-base text-navy">
            {t('profile.address.title')}
          </h2>
          <span className="text-xs font-mono text-navy/40">
            {addressSaving ? '…' : addressSaved ? `✓ ${t('common.save')}` : ''}
          </span>
        </div>
        <AddressForm
          value={{
            receiving_country_iso: user?.receiving_country_iso ?? null,
            receiving_city: user?.receiving_city ?? null,
            receiving_city_geoname_id: user?.receiving_city_geoname_id ?? null,
            receiving_street: user?.receiving_street ?? null,
            receiving_postal_code: user?.receiving_postal_code ?? null,
            receiving_note: user?.receiving_note ?? null,
          }}
          onChange={handleAddressChange}
          countryOptions={countryOptions}
        />
      </div>

      <VerificationSection />

      <TrustCirclesSection />

      <KeypairSection />

      <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display font-semibold text-base text-navy">{t('profile.invites')}</h2>
          <button
            type="button"
            onClick={handleCreateInvite}
            disabled={creatingInvite}
            className="text-xs font-body text-cyan hover:underline disabled:opacity-50"
          >
            {creatingInvite ? t('common.sending') : t('profile.inviteCreate')}
          </button>
        </div>
        {invitesLoading ? (
          <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
        ) : invites.length === 0 ? (
          <p className="text-sm font-body text-navy/40">{t('profile.noInvites')}</p>
        ) : (
          <div className="space-y-2">
            {invites.map((inv) => {
              const statusColor =
                inv.status === 'accepted'
                  ? 'bg-green-100 text-green-700'
                  : inv.status === 'expired'
                  ? 'bg-navy/10 text-navy/50'
                  : 'bg-cyan/10 text-cyan'
              return (
                <div key={inv.token} className="flex items-center justify-between py-2 border-b border-navy/5 last:border-0 gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-xs font-mono px-2 py-0.5 rounded ${statusColor}`}>
                        {t(`profile.inviteStatus.${inv.status}`)}
                      </span>
                      {inv.status === 'pending' && (
                        <span className="text-xs font-mono text-navy/40">
                          {t('profile.inviteExpiresIn', { time: formatRemaining(inv.expires_at) })}
                        </span>
                      )}
                      {inv.status === 'accepted' && inv.accepted_by_display_name && (
                        <span className="text-xs font-body text-navy/60">
                          → {inv.accepted_by_display_name}
                        </span>
                      )}
                    </div>
                    <MonoText className="text-xs text-navy/30 truncate mt-0.5">
                      {inv.token.slice(0, 24)}…
                    </MonoText>
                  </div>
                  {inv.status === 'pending' && (
                    <button
                      type="button"
                      onClick={() => copyInviteLink(inv.token)}
                      className="text-xs font-body text-cyan/70 hover:text-cyan shrink-0"
                    >
                      {t('profile.inviteCopy')}
                    </button>
                  )}
                </div>
              )
            })}
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
