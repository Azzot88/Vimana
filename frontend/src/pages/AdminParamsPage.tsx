import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import {
  listParams,
  paramHistory,
  setParam,
  type ParamCurrent,
  type ParamVersion,
} from '../api/platformParams'
import MonoText from '../components/MonoText'

/** T3.40 — business-logic parameters.
 *
 *  Three things the screen has to make visible, because getting them wrong
 *  costs money rather than looks:
 *   - whether a number is a built-in default or something somebody chose;
 *   - whether it applies globally or only to the corridor being viewed;
 *   - who last changed it and why.
 *  Everything else is a form.
 */
const GROUP_ORDER = ['fees', 'bond', 'premium'] as const

export default function AdminParamsPage() {
  const { t } = useTranslation()
  const me = useAuthStore((s) => s.user)

  const [scope, setScope] = useState('global')
  const [scopeInput, setScopeInput] = useState('')
  const [params, setParams] = useState<ParamCurrent[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const [editing, setEditing] = useState<string | null>(null)
  const [draftValue, setDraftValue] = useState('')
  const [draftComment, setDraftComment] = useState('')
  const [saving, setSaving] = useState(false)

  const [historyFor, setHistoryFor] = useState<string | null>(null)
  const [history, setHistory] = useState<ParamVersion[]>([])

  const reload = async (nextScope = scope) => {
    setLoading(true)
    setError('')
    try {
      setParams(await listParams(nextScope))
    } catch {
      setError(t('adminParams.loadError'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void reload(scope)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope])

  if (me?.role !== 'superuser') return <Navigate to="/dashboard" replace />

  const applyScope = () => {
    const next = scopeInput.trim().toUpperCase()
    setScope(next === '' ? 'global' : next)
  }

  const startEdit = (p: ParamCurrent) => {
    setEditing(p.key)
    setDraftValue(p.value)
    setDraftComment('')
  }

  const save = async (p: ParamCurrent) => {
    setSaving(true)
    setError('')
    try {
      await setParam({
        key: p.key,
        value: draftValue,
        scope,
        comment: draftComment,
      })
      setEditing(null)
      await reload()
    } catch {
      setError(t('adminParams.saveError'))
    } finally {
      setSaving(false)
    }
  }

  const toggleHistory = async (key: string) => {
    if (historyFor === key) {
      setHistoryFor(null)
      return
    }
    setHistoryFor(key)
    try {
      setHistory(await paramHistory(key))
    } catch {
      setHistory([])
    }
  }

  const sourceBadge = (source: ParamCurrent['source']) => {
    const tone =
      source === 'corridor'
        ? 'bg-amber/15 text-amber'
        : source === 'global'
          ? 'bg-cyan/15 text-cyan'
          : 'bg-navy/10 text-navy/50'
    return (
      <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono uppercase ${tone}`}>
        {t(`adminParams.source.${source}`)}
      </span>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-display font-semibold text-navy">
        {t('adminParams.title')}
      </h1>
      <p className="text-sm font-body text-navy/50 mt-1">{t('adminParams.hint')}</p>

      <div className="mt-6 flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-body font-medium text-navy/40 mb-1">
            {t('adminParams.scope')}
          </label>
          <input
            value={scopeInput}
            onChange={(e) => setScopeInput(e.target.value)}
            placeholder="AE->US"
            className="px-3 py-2 rounded-lg border border-navy/15 font-mono text-sm"
          />
        </div>
        <button
          onClick={applyScope}
          className="px-4 py-2 rounded-lg bg-navy text-white text-sm font-body"
        >
          {t('adminParams.apply')}
        </button>
        <MonoText className="text-xs text-navy/40">
          {t('adminParams.viewing')}: {scope}
        </MonoText>
      </div>

      {error && <p className="mt-4 text-sm font-body text-danger">{error}</p>}
      {loading && <p className="mt-4 text-sm font-body text-navy/40">{t('common.loading')}</p>}

      {GROUP_ORDER.map((group) => {
        const rows = params.filter((p) => p.group === group)
        if (rows.length === 0) return null
        return (
          <section key={group} className="mt-8">
            <h2 className="text-xs font-mono uppercase tracking-widest text-navy/40">
              {t(`adminParams.group.${group}`)}
            </h2>
            <div className="mt-3 space-y-2">
              {rows.map((p) => (
                <div
                  key={p.key}
                  className="rounded-2xl border border-navy/10 bg-surface p-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <MonoText className="text-sm text-navy">{p.key}</MonoText>
                    {sourceBadge(p.source)}
                    {!p.approved && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono uppercase bg-amber/15 text-amber">
                        {t('adminParams.proposed')}
                      </span>
                    )}
                    <span className="ml-auto font-mono text-lg text-navy">
                      {p.value}
                      {p.value_type === 'percent' ? '%' : ''}
                    </span>
                  </div>

                  <p className="mt-1 text-xs font-body text-navy/50">{p.note}</p>
                  {p.comment && (
                    <p className="mt-1 text-xs font-body text-navy/40 italic">{p.comment}</p>
                  )}

                  {editing === p.key ? (
                    <div className="mt-3 flex flex-wrap gap-2 items-end">
                      <input
                        value={draftValue}
                        onChange={(e) => setDraftValue(e.target.value)}
                        className="px-3 py-2 rounded-lg border border-navy/15 font-mono text-sm w-32"
                      />
                      <input
                        value={draftComment}
                        onChange={(e) => setDraftComment(e.target.value)}
                        placeholder={t('adminParams.reason')}
                        className="px-3 py-2 rounded-lg border border-navy/15 font-body text-sm flex-1 min-w-[12rem]"
                      />
                      <button
                        disabled={saving}
                        onClick={() => save(p)}
                        className="px-4 py-2 rounded-lg bg-amber text-navy text-sm font-body disabled:opacity-50"
                      >
                        {saving ? '...' : t('adminParams.save')}
                      </button>
                      <button
                        onClick={() => setEditing(null)}
                        className="px-4 py-2 rounded-lg border border-navy/15 text-sm font-body"
                      >
                        {t('common.cancel')}
                      </button>
                    </div>
                  ) : (
                    <div className="mt-3 flex gap-3">
                      <button
                        onClick={() => startEdit(p)}
                        className="text-xs font-body text-cyan"
                      >
                        {t('adminParams.change')}
                      </button>
                      <button
                        onClick={() => toggleHistory(p.key)}
                        className="text-xs font-body text-navy/40"
                      >
                        {t('adminParams.history')}
                      </button>
                    </div>
                  )}

                  {historyFor === p.key && (
                    <div className="mt-3 border-t border-navy/10 pt-3 space-y-1">
                      {history.length === 0 && (
                        <p className="text-xs font-body text-navy/40">
                          {t('adminParams.noHistory')}
                        </p>
                      )}
                      {history.map((h) => (
                        <div key={h.id} className="flex flex-wrap gap-2 text-xs">
                          <MonoText className="text-navy/60">{h.value}</MonoText>
                          <span className="font-mono text-navy/30">{h.scope}</span>
                          <span className="font-body text-navy/40">
                            {new Date(h.effective_from).toLocaleString()}
                          </span>
                          {h.comment && (
                            <span className="font-body text-navy/40 italic">{h.comment}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
