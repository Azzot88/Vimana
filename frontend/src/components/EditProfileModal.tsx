import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { parsePhoneNumberFromString, getCountryCallingCode } from 'libphonenumber-js/min'
import type { CountryCode } from 'libphonenumber-js/min'
import { updateMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import CountryCodeSelect from './CountryCodeSelect'

interface Props {
  open: boolean
  onClose: () => void
}

/** T_UX.4 B — single Edit modal for basic profile fields (name, phone).
 *  Addresses live in their own AddressesSection and are edited inline.
 *  Avatar upload is a future increment (needs storage endpoint). */
export default function EditProfileModal({ open, onClose }: Props) {
  const { t } = useTranslation()
  const { user, token, setAuth } = useAuthStore()

  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const parsed = user?.phone ? parsePhoneNumberFromString(user.phone) : null
  const [phoneIso, setPhoneIso] = useState<CountryCode | ''>(
    (parsed?.country ?? '') as CountryCode | '',
  )
  const [phoneNational, setPhoneNational] = useState<string>(
    parsed?.nationalNumber ?? (user?.phone ?? '').replace(/^\+\d+/, ''),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || !user) return
    setDisplayName(user.display_name ?? '')
    const p = user.phone ? parsePhoneNumberFromString(user.phone) : null
    setPhoneIso((p?.country ?? '') as CountryCode | '')
    setPhoneNational(p?.nationalNumber ?? (user.phone ?? '').replace(/^\+\d+/, ''))
    setError('')
  }, [open, user])

  if (!open) return null

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      const patch: Record<string, string | undefined> = {}
      if (displayName.trim() && displayName !== user?.display_name) {
        patch.display_name = displayName.trim()
      }
      if (phoneIso && phoneNational) {
        const dial = getCountryCallingCode(phoneIso as CountryCode)
        const composed = `+${dial}${phoneNational.replace(/\D/g, '')}`
        if (composed !== user?.phone) patch.phone = composed
      }
      if (Object.keys(patch).length > 0) {
        const { data } = await updateMe(patch)
        setAuth(data, token!)
      }
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('common.errorGeneric') as string)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl"
      >
        <h3 className="font-display font-semibold text-lg text-navy">
          {t('profile.editTitle')}
        </h3>

        <div>
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">
            {t('auth.name')}
          </label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={120}
            className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
          />
        </div>

        <div>
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">
            {t('auth.phone')}
          </label>
          <div className="flex flex-col sm:flex-row gap-2 sm:items-start">
            <CountryCodeSelect value={phoneIso} onChange={setPhoneIso} />
            <input
              type="tel"
              inputMode="numeric"
              value={phoneNational}
              onChange={(e) => setPhoneNational(e.target.value)}
              placeholder="555 000 0000"
              className="flex-1 border border-navy/20 rounded-lg px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan"
            />
          </div>
        </div>

        <p className="text-xs font-mono text-navy/40">{t('profile.editHint')}</p>

        {error && <p className="text-xs font-mono text-red-600">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="text-sm font-body text-navy/60 hover:text-navy px-4 py-2"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="bg-navy text-ivory font-display font-medium text-sm px-5 py-2 rounded-lg hover:bg-navy-mid disabled:opacity-50"
          >
            {saving ? t('common.sending') : t('common.save')}
          </button>
        </div>
      </div>
    </div>
  )
}
