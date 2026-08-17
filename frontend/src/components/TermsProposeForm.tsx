import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { proposeTerms } from '../api/terms'

/** T3.35 — proposing, or countering.
 *
 *  Deliberately short. The carrier's baseline already lives on the trip; this
 *  is the place where either side names a different number, and asking for ten
 *  fields to do that is how a counter-offer stops happening.
 */
interface Props {
  dealId: string
  supersedesId?: string | null
  onDone: () => void
}

export default function TermsProposeForm({ dealId, supersedesId, onDone }: Props) {
  const { t } = useTranslation()
  const [weight, setWeight] = useState('')
  const [price, setPrice] = useState('')
  const [declared, setDeclared] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await proposeTerms(dealId, {
        weight_kg: Number(weight),
        price_total: Number(price),
        declared_value: Number(declared || 0),
        description: description || null,
        supersedes_id: supersedesId ?? null,
      })
      setWeight('')
      setPrice('')
      setDeclared('')
      setDescription('')
      onDone()
    } catch {
      setError(t('terms.proposeFailed'))
    } finally {
      setBusy(false)
    }
  }

  const field = (
    label: string,
    value: string,
    setter: (v: string) => void,
    type = 'number',
  ) => (
    <label className="flex-1 min-w-[7rem]">
      <span className="block text-xs font-body text-navy/40 mb-1">{label}</span>
      <input
        type={type}
        step="any"
        min="0"
        required={type === 'number'}
        value={value}
        onChange={(e) => setter(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border border-navy/15 font-mono text-sm"
      />
    </label>
  )

  return (
    <form onSubmit={submit} className="rounded-2xl border border-navy/10 bg-surface p-4">
      <p className="text-sm font-display font-semibold text-navy mb-3">
        {supersedesId ? t('terms.counterTitle') : t('terms.proposeTitle')}
      </p>
      <div className="flex flex-wrap gap-3">
        {field(t('terms.weight'), weight, setWeight)}
        {field(t('terms.price'), price, setPrice)}
        {field(t('terms.declaredValue'), declared, setDeclared)}
      </div>
      <label className="block mt-3">
        <span className="block text-xs font-body text-navy/40 mb-1">
          {t('terms.cargoDescription')}
        </span>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm"
        />
      </label>
      {error && <p className="mt-2 text-xs font-body text-danger">{error}</p>}
      <button
        type="submit"
        disabled={busy}
        className="mt-3 px-4 py-2 rounded-lg bg-navy text-white text-sm font-body disabled:opacity-50"
      >
        {busy ? '...' : t('terms.send')}
      </button>
    </form>
  )
}
