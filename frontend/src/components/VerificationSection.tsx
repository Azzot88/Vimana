import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  getUserVerifications,
  revokeBadge,
  selfUpload,
  type UserVerificationSummary,
  type VerificationBadge,
  type VerificationLevel,
} from '../api/verification'
import { useAuthStore } from '../stores/auth'
import MonoText from './MonoText'
import VerificationBadgeChip from './VerificationBadgeChip'

const DOC_TYPES = ['passport', 'driver_license', 'national_id', 'other']

export default function VerificationSection() {
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [summary, setSummary] = useState<UserVerificationSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [docType, setDocType] = useState('passport')
  const [docCountry, setDocCountry] = useState('')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    if (!user) return
    try {
      const { data } = await getUserVerifications(user.id)
      setSummary(data)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !docCountry) {
      setError(t('verification.pickCountry') as string)
      return
    }
    setUploading(true)
    setError('')
    try {
      await selfUpload(file, docType, docCountry.toUpperCase())
      await load()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : (t('verification.uploadError') as string))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleRevoke = async (badgeId: string) => {
    if (!window.confirm(t('verification.revokeConfirm') as string)) return
    try {
      await revokeBadge(badgeId)
      await load()
    } catch {
      // silent
    }
  }

  const renderBadge = (b: VerificationBadge) => {
    const active = !b.revoked_at
    return (
      <div
        key={b.id}
        className={`flex items-center justify-between py-2 border-b border-navy/5 last:border-0 ${
          active ? '' : 'opacity-50'
        }`}
      >
        <div className="flex items-center gap-3">
          <VerificationBadgeChip level={b.level} at={b.verified_at} />
          <div>
            <MonoText className="text-xs text-navy/40">
              {t(`verification.source.${b.source}`)}
            </MonoText>
            {/* T_TRUST.1 — expiry belongs next to the badge, not only in the
                database. It is the difference between "verified" and "was
                verified", and the account holder is the person who can act on
                it before it lapses. */}
            {b.expires_at && (
              <MonoText className="text-xs text-navy/30">
                {t(
                  new Date(b.expires_at) < new Date()
                    ? 'verification.expiredOn'
                    : 'verification.expiresOn',
                  { date: new Date(b.expires_at).toLocaleDateString(i18n.language) },
                )}
              </MonoText>
            )}
          </div>
        </div>
        {active && b.source === 'auto_ocr' && (
          <button
            type="button"
            onClick={() => handleRevoke(b.id)}
            className="text-xs font-body text-navy/40 hover:text-danger"
          >
            {t('verification.revoke')}
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display font-semibold text-base text-navy">
          {t('verification.sectionTitle')}
        </h2>
        <VerificationBadgeChip
          level={summary?.highest_level}
          at={summary?.highest_level_at}
          size="md"
        />
      </div>

      <p className="text-xs font-body text-navy/50">
        {t('verification.sectionHint')}
      </p>

      {loading ? (
        <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 text-center">
            {(['auto', 'peer', 'kyc'] as VerificationLevel[]).map((l) => (
              <div key={l} className="bg-ivory rounded-field py-2">
                <MonoText className="text-lg text-navy font-medium">
                  {summary?.active_counts[l] ?? 0}
                </MonoText>
                <p className="text-xs font-body text-navy/40">
                  {t(`verification.level.${l}`)}
                </p>
              </div>
            ))}
          </div>

          {summary && summary.badges.length > 0 && (
            <div className="space-y-1 pt-2 border-t border-navy/5">
              {summary.badges.map(renderBadge)}
            </div>
          )}

          <div className="pt-3 border-t border-navy/5 space-y-2">
            <p className="text-xs font-display font-semibold text-navy/60 uppercase tracking-wide">
              {t('verification.uploadTitle')}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {/* T_TEST.8 — a control whose only description is the option it
                  happens to be showing has no name at all for a screen reader.
                  The visible heading above says "Self-verify", not what this
                  picks, so an `aria-label` is the honest fix rather than
                  pointing at it with `aria-labelledby`. */}
              <select
                aria-label={t('verification.docTypeLabel')}
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                className="border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy bg-white focus:outline-none focus:border-cyan"
              >
                {DOC_TYPES.map((d) => (
                  <option key={d} value={d}>
                    {t(`verification.docType.${d}`)}
                  </option>
                ))}
              </select>
              <input
                type="text"
                aria-label={t('verification.docCountryLabel')}
                value={docCountry}
                onChange={(e) => setDocCountry(e.target.value.toUpperCase().slice(0, 2))}
                placeholder="AE"
                maxLength={2}
                className="border border-navy/20 rounded-field px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan"
              />
            </div>
            <label className="inline-flex cursor-pointer border border-cyan/40 text-cyan rounded-field px-4 py-2 text-xs font-display font-medium hover:bg-cyan/10 transition-colors">
              {uploading ? '…' : `📎 ${t('verification.uploadButton')}`}
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,application/pdf"
                onChange={handleUpload}
                className="hidden"
                disabled={uploading}
              />
            </label>
            <p className="text-[10px] font-mono text-navy/30">
              🔒 {t('verification.privacyHint')}
            </p>
            {error && <p className="text-xs font-mono text-danger">{error}</p>}
          </div>
        </>
      )}
    </div>
  )
}
