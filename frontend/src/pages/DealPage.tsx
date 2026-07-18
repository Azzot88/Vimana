import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, Link } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { openDispute } from '../api/admin'
import { getDeal, acceptDeal, addEvent, confirmDeal, type DealDetail } from '../api/deals'
import { listDealRequests, type VerificationRequest as VerificationRequestT } from '../api/verification'
import StatusBadge from '../components/StatusBadge'
import MonoText from '../components/MonoText'
import VerificationDeclineBanner from '../components/VerificationDeclineBanner'
import VerificationRequestModal from '../components/VerificationRequestModal'
import VerificationRespondModal from '../components/VerificationRespondModal'

export default function DealPage() {
  const { t } = useTranslation()
  const { dealId } = useParams<{ dealId: string }>()
  const user = useAuthStore((s) => s.user)
  const [deal, setDeal] = useState<DealDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [disputeOpen, setDisputeOpen] = useState(false)
  const [disputeReason, setDisputeReason] = useState('')
  const [disputeSubmitting, setDisputeSubmitting] = useState(false)
  const [disputeError, setDisputeError] = useState('')
  const [disputeCreated, setDisputeCreated] = useState(false)
  const [verifyRequestFor, setVerifyRequestFor] = useState<'sender' | 'carrier' | null>(null)
  const [pendingRespond, setPendingRespond] = useState<VerificationRequestT | null>(null)
  const [verifySuccess, setVerifySuccess] = useState(false)

  const handleDispute = async () => {
    if (!dealId || !disputeReason.trim()) return
    setDisputeSubmitting(true)
    setDisputeError('')
    try {
      await openDispute(dealId, disputeReason.trim())
      setDisputeCreated(true)
      setDisputeOpen(false)
      setDisputeReason('')
      await load()
    } catch {
      setDisputeError(t('dispute.openError'))
    } finally {
      setDisputeSubmitting(false)
    }
  }

  const [openRequestForMe, setOpenRequestForMe] = useState<VerificationRequestT | null>(null)
  const [carrierPoliteDecline, setCarrierPoliteDecline] = useState<VerificationRequestT | null>(null)

  const load = async () => {
    if (!dealId) return
    try {
      const { data } = await getDeal(dealId)
      setDeal(data)
      // Also check if there's a pending verification request targeted at me,
      // AND if carrier polite-declined an identity request from sender (T2.1
      // pt.3 / T_UX.1: show reassurance banner + collateral CTA on sender's
      // side).
      try {
        const { data: reqs } = await listDealRequests(dealId)
        const currentId = user?.id
        const myRole = data.carrier_id === currentId ? 'carrier' : data.sender_id === currentId ? 'sender' : null
        const pending = reqs.find(
          (r) => r.status === 'pending' && r.target_role === myRole,
        )
        setOpenRequestForMe(pending ?? null)

        const politeDecline = reqs.find(
          (r) => r.status === 'declined_polite' && r.target_role === 'carrier',
        )
        setCarrierPoliteDecline(politeDecline ?? null)
      } catch {
        setOpenRequestForMe(null)
        setCarrierPoliteDecline(null)
      }
    } catch {
      setError('Сделка не найдена')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [dealId, user?.id])

  const handleAction = async (action: 'accept' | 'handoff' | 'confirm') => {
    if (!dealId) return
    setActionLoading(true)
    setError('')
    try {
      if (action === 'accept') {
        await acceptDeal(dealId)
        await load()
      } else if (action === 'handoff') {
        await addEvent(dealId, 'handoff', 'Груз передан перевозчику')
        await load()
      } else if (action === 'confirm') {
        await confirmDeal(dealId)
        await load()
      }
    } catch {
      setError('Действие не выполнено')
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-navy/40 text-sm">Загрузка...</MonoText>
      </div>
    )
  }

  if (!deal) {
    return (
      <div className="text-center py-24">
        <p className="text-sm font-body text-navy/40">{error || 'Сделка не найдена'}</p>
      </div>
    )
  }

  const isCarrier = deal.carrier_id === user?.id
  const isSender = deal.sender_id === user?.id

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/deals" className="text-xs font-body text-navy/40 hover:text-navy transition-colors">
          ← Сделки
        </Link>
      </div>

      <div className="bg-white rounded-xl border border-navy/10 overflow-hidden">
        <div className="bg-navy px-4 py-4 sm:px-6 sm:py-5">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div className="space-y-1">
              <p className="text-xs font-mono text-white/40 uppercase tracking-widest">Посадочный талон</p>
              <MonoText className="text-xl text-white font-medium">
                {deal.origin} → {deal.destination}
              </MonoText>
              <MonoText className="text-sm text-white/60">
                {new Date(deal.depart_at).toLocaleString('ru-RU')}
              </MonoText>
            </div>
            <div className="self-start"><StatusBadge status={deal.status} /></div>
          </div>
        </div>

        <div className="p-4 sm:p-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">Отправитель</p>
            <p className="text-sm font-body text-navy font-medium">{deal.sender_name}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">Перевозчик</p>
            <p className="text-sm font-body text-navy font-medium">{deal.carrier_name}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">Груз</p>
            <p className="text-sm font-body text-navy">{deal.cargo_description}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">Категория</p>
            <MonoText className="text-sm text-navy">{deal.cargo_category}</MonoText>
          </div>
          <div className="sm:col-span-2">
            <p className="text-xs font-body font-medium text-navy/40 mb-1">ID сделки</p>
            <MonoText className="text-xs text-navy/50 break-all">{deal.id}</MonoText>
          </div>
        </div>

        {error && (
          <div className="px-4 sm:px-6 pb-4">
            <p className="text-xs font-mono text-orange-600">{error}</p>
          </div>
        )}

        <div className="px-4 sm:px-6 pb-6 flex flex-col sm:flex-row sm:flex-wrap gap-3">
          {isCarrier && deal.status === 'matched' && (
            <button
              onClick={() => handleAction('accept')}
              disabled={actionLoading}
              className="bg-cyan text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {actionLoading ? '...' : 'Принять сделку'}
            </button>
          )}
          {isCarrier && deal.status === 'accepted' && (
            <button
              onClick={() => handleAction('handoff')}
              disabled={actionLoading}
              className="bg-amber text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {actionLoading ? '...' : 'Зафиксировать передачу'}
            </button>
          )}
          {isSender && deal.status === 'delivered' && (
            <button
              onClick={() => handleAction('confirm')}
              disabled={actionLoading}
              className="bg-green-600 text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {actionLoading ? '...' : 'Подтвердить получение'}
            </button>
          )}
          <Link
            to={`/deals/${deal.id}/vault`}
            className="border border-navy/20 text-navy font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:border-cyan transition-colors text-center"
          >
            DealVault →
          </Link>
          {isCarrier &&
            ['matched', 'accepted', 'in_transit'].includes(deal.status) && (
              <button
                onClick={() => setVerifyRequestFor('sender')}
                className="border border-cyan/40 text-cyan font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:bg-cyan/10 transition-colors"
              >
                {t('verification.askSenderButton')}
              </button>
            )}
          {isSender &&
            ['matched', 'accepted', 'in_transit'].includes(deal.status) && (
              <button
                onClick={() => setVerifyRequestFor('carrier')}
                className="border border-cyan/40 text-cyan font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:bg-cyan/10 transition-colors"
              >
                {t('verification.askCarrierButton')}
              </button>
            )}
          {(isCarrier || isSender) &&
            ['accepted', 'in_transit', 'delivered'].includes(deal.status) &&
            deal.status !== 'disputed' && (
              <button
                onClick={() => setDisputeOpen(true)}
                className="border border-red-300 text-red-600 font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:bg-red-50 transition-colors"
              >
                {t('dispute.openButton')}
              </button>
            )}
        </div>
      </div>

      {disputeCreated && (
        <div className="bg-amber/10 border border-amber/40 rounded-xl p-4">
          <p className="text-sm font-body text-navy">{t('dispute.createdNotice')}</p>
        </div>
      )}

      {verifySuccess && (
        <div className="bg-cyan/10 border border-cyan/40 rounded-xl p-4">
          <p className="text-sm font-body text-navy">{t('verification.requestSent')}</p>
        </div>
      )}

      {openRequestForMe && !pendingRespond && (
        <div className="bg-amber/10 border border-amber/40 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-sm font-body text-navy">
            ⚠️ {t('verification.pendingForYou')}
          </p>
          <button
            onClick={() => setPendingRespond(openRequestForMe)}
            className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid"
          >
            {t('verification.respondButton')}
          </button>
        </div>
      )}

      {isSender && carrierPoliteDecline && (
        <VerificationDeclineBanner />
      )}

      {verifyRequestFor && dealId && (
        <VerificationRequestModal
          dealId={dealId}
          targetRole={verifyRequestFor}
          onClose={() => setVerifyRequestFor(null)}
          onCreated={() => {
            setVerifyRequestFor(null)
            setVerifySuccess(true)
          }}
        />
      )}

      {pendingRespond && (
        <VerificationRespondModal
          request={pendingRespond}
          yourRole={isCarrier ? 'carrier' : 'sender'}
          onClose={() => setPendingRespond(null)}
          onDone={() => {
            setPendingRespond(null)
            load()
          }}
        />
      )}

      {disputeOpen && (
        <div
          className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setDisputeOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <h2 className="font-display font-semibold text-lg text-navy">
              {t('dispute.modalTitle')}
            </h2>
            <p className="text-sm font-body text-navy/60">
              {t('dispute.modalHint')}
            </p>
            <textarea
              value={disputeReason}
              onChange={(e) => setDisputeReason(e.target.value)}
              rows={4}
              placeholder={t('dispute.reasonPlaceholder') as string}
              className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            />
            {disputeError && (
              <p className="text-xs font-mono text-red-600">{disputeError}</p>
            )}
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setDisputeOpen(false)}
                className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleDispute}
                disabled={disputeSubmitting || !disputeReason.trim()}
                className="bg-red-600 text-white font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-red-700 transition-colors disabled:opacity-40"
              >
                {disputeSubmitting ? '…' : t('dispute.submit')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
