import { useTranslation } from 'react-i18next'
import type { VerificationLevel } from '../api/verification'

const STYLES: Record<VerificationLevel, string> = {
  auto: 'bg-navy/10 text-navy/70',
  peer: 'bg-cyan/20 text-cyan',
  kyc: 'bg-amber/20 text-amber',
}

const ICONS: Record<VerificationLevel, string> = {
  auto: '🔓',
  peer: '👤',
  kyc: '🛡️',
}

/**
 * T_TRUST.1 — a verification level, never without the date it rests on
 * (`D-EVIDENCE-DECAYS`).
 *
 * `at` is a **required** prop, deliberately. "Verified" reads as a present-tense
 * fact; what happened is that somebody checked something on a particular day,
 * and a year later that is a weaker statement. Had the date been optional,
 * forgetting it would be the path of least resistance and the bare badge would
 * creep back one call site at a time. Required means the compiler asks the
 * question instead of a reviewer.
 *
 * `null` is an accepted answer — some evidence genuinely has no date — and it
 * renders as "date unknown" rather than as a clean badge. That reads worse than
 * a date, which is exactly right: it is worse.
 */
interface Props {
  level: VerificationLevel | null | undefined
  /** When the badge was issued. `null` when unknown — and shown as such. */
  at: string | null | undefined
  size?: 'sm' | 'md'
}

export default function VerificationBadgeChip({ level, at, size = 'sm' }: Props) {
  const { t, i18n } = useTranslation()
  if (!level) return null
  const padding = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'
  const date = at ? new Date(at).toLocaleDateString(i18n.language) : null
  return (
    <span
      className={`inline-flex items-center gap-1 rounded font-mono ${padding} ${STYLES[level]}`}
      title={t(`verification.level.${level}Hint`) as string}
    >
      <span aria-hidden="true">{ICONS[level]}</span>
      <span>{t(`verification.level.${level}`)}</span>
      <span className="opacity-60" data-testid="badge-date">
        · {date ?? t('verification.dateUnknown')}
      </span>
    </span>
  )
}
