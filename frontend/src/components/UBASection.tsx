import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getMyUba, type UBAResponse, type UBALevel } from '../api/uba'
import MonoText from './MonoText'

const LEVEL_CLASS: Record<UBALevel, string> = {
  newbie:   'bg-navy/10 text-navy',
  verified: 'bg-cyan/20 text-cyan',
  reliable: 'bg-cyan/25 text-cyan',
  trusted:  'bg-amber/20 text-amber',
  elite:    'bg-amber/30 text-amber',
}

export default function UBASection() {
  const { t } = useTranslation()
  const [data, setData] = useState<UBAResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMyUba()
      .then(({ data }) => setData(data))
      .catch(() => {
        // silent — UBA is a display concern, not a blocking one.
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-navy/10 p-6">
        <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display font-semibold text-base text-navy">
          {t('profile.uba.title')}
        </h2>
        <span
          className={`text-xs font-mono px-2 py-0.5 rounded ${LEVEL_CLASS[data.level]}`}
        >
          {t(`profile.uba.levels.${data.level}`)}
        </span>
      </div>

      <div className="flex items-baseline gap-2">
        <MonoText className="text-4xl text-navy tabular-nums">{data.uba}</MonoText>
        <MonoText className="text-xs text-navy/40">/ 1000</MonoText>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2 border-t border-navy/5">
        <Tile
          label={t('profile.uba.components.f')}
          value={data.components.f_count}
          hint={t('profile.uba.components.fHint')}
        />
        <Tile
          label={t('profile.uba.components.q')}
          value={data.components.q_count}
          hint={t('profile.uba.components.qHint')}
        />
        <Tile
          label={t('profile.uba.components.v')}
          value={`$${Math.round(data.components.v_sum)}`}
          hint={t('profile.uba.components.vHint')}
        />
        <Tile
          label={t('profile.uba.components.d')}
          value={`$${Math.round(data.components.d_peak)}`}
          hint={t('profile.uba.components.dHint')}
        />
      </div>

      <p className="text-xs font-body text-navy/50">
        {t('profile.uba.hint')}
      </p>
    </div>
  )
}

function Tile({
  label,
  value,
  hint,
}: {
  label: string
  value: string | number
  hint: string
}) {
  return (
    <div className="bg-ivory rounded-lg px-3 py-2">
      <p className="text-xs font-body text-navy/50">{label}</p>
      <MonoText className="text-lg text-navy tabular-nums">{value}</MonoText>
      <p className="text-xs font-body text-navy/40 mt-1 leading-tight">{hint}</p>
    </div>
  )
}
