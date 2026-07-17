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

interface Props {
  level: VerificationLevel | null | undefined
  size?: 'sm' | 'md'
}

export default function VerificationBadgeChip({ level, size = 'sm' }: Props) {
  const { t } = useTranslation()
  if (!level) return null
  const padding = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'
  return (
    <span
      className={`inline-flex items-center gap-1 rounded font-mono ${padding} ${STYLES[level]}`}
      title={t(`verification.level.${level}Hint`) as string}
    >
      <span aria-hidden="true">{ICONS[level]}</span>
      <span>{t(`verification.level.${level}`)}</span>
    </span>
  )
}
