import { useTranslation } from 'react-i18next'
import type { UBALevel } from '../api/uba'

const LEVEL_CLASS: Record<UBALevel, string> = {
  newbie:   'bg-navy/10 text-navy/70',
  verified: 'bg-cyan/15 text-cyan',
  reliable: 'bg-cyan/25 text-cyan',
  trusted:  'bg-amber/20 text-amber',
  elite:    'bg-amber/35 text-amber',
}

interface Props {
  uba: number | null | undefined
  level: UBALevel | null | undefined
  size?: 'sm' | 'md'
}

/** Compact carrier-trust badge for cards and lists.
 *  Renders nothing if UBA hasn't been computed for the user yet. */
export default function UBAChip({ uba, level, size = 'sm' }: Props) {
  const { t } = useTranslation()
  if (level == null || uba == null) return null
  const pad = size === 'sm' ? 'px-1.5 py-0.5' : 'px-2 py-0.5'
  return (
    <span
      title={t('profile.uba.title') as string}
      className={`inline-flex items-center gap-1 rounded ${pad} text-xs font-mono ${LEVEL_CLASS[level]}`}
    >
      <span className="tabular-nums">{uba}</span>
      <span className="opacity-70">·</span>
      <span>{t(`profile.uba.levels.${level}`)}</span>
    </span>
  )
}
