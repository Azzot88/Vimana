import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, Link } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { openDispute } from '../api/admin'
import { getDeal, acceptDeal, addEvent, confirmDeal, type DealDetail } from '../api/deals'
import { listDealRequests, type VerificationRequest as VerificationRequestT } from '../api/verification'
import StatusBadge from '../components/StatusBadge'
import MonoText from '../components/MonoText'
import PlatformNoticeBanner from '../components/PlatformNoticeBanner'
import RouteNoteBadge from '../components/RouteNoteBadge'
import VerificationDeclineBanner from '../components/VerificationDeclineBanner'
import VerificationRequestModal from '../components/VerificationRequestModal'
import VerificationRespondModal from '../components/VerificationRespondModal'
import { useRouteNotes } from '../hooks/useRouteNotes'

export default function DealPage() {
  const { t } = useTranslation()
  const { dealId } = useParams<{ dealId: string }>()
  const user = useAuthStore((s) => s.user)
  const [deal, setDeal] = useState<DealDetail | null>(null)
  const [loading, setLoading] = useState(true)
  // T_UX.2 pt.3 — RouteNotes for this corridor (empty until deal loads).
  const { notes: routeNotes } = useRouteNotes(deal?.origin, deal?.destination)
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
      setError(t('deals.notFound'))
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
        // T_UX.7 pt.3 — no free-text note. It was persisted into the event payload
        // and hashed into the chain, so one party's UI language ended up inside
        // shared evidence the other party reads. `event_type` already says
        // exactly this, and both sides render it in their own language.
        await addEvent(dealId, 'handoff')
        await load()
      } else if (action === 'confirm') {
        await confirmDeal(dealId)
        await load()
      }
    } catch {
      setError(t('deals.actionFailed'))
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-muted text-sm">{t('common.loading')}</MonoText>
      </div>
    )
  }

  if (!deal) {
    return (
      <div className="text-center py-24">
        <p className="text-sm font-body text-muted">{error || t('deals.notFound')}</p>
      </div>
    )
  }

  const isCarrier = deal.carrier_id === user?.id
  const isSender = deal.sender_id === user?.id

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/deals" className="text-xs font-body text-muted hover:text-navy transition-colors">
          ← {t('nav.deals')}
        </Link>
      </div>

      <PlatformNoticeBanner surface="deal_page" />
      {routeNotes.length > 0 && (
        <div className="space-y-2">
          {routeNotes.map((n) => (
            <RouteNoteBadge key={n.id} note={n} />
          ))}
        </div>
      )}

      <div className="bg-white rounded-card border border-navy/10 overflow-hidden">
        <div className="bg-navy px-4 py-4 sm:px-6 sm:py-5">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div className="space-y-1">
              <p className="text-xs font-mono text-white/70 uppercase tracking-widest">{t('deals.boardingPass')}</p>
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
            <p className="text-xs font-body font-medium text-muted mb-1">{t('deals.sender')}</p>
            <p className="text-sm font-body text-navy font-medium">{deal.sender_name}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-muted mb-1">{t('deals.carrier')}</p>
            <p className="text-sm font-body text-navy font-medium">{deal.carrier_name}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-muted mb-1">{t('deals.cargo')}</p>
            <p className="text-sm font-body text-navy">{deal.cargo_description}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-muted mb-1">{t('deals.category')}</p>
            <MonoText className="text-sm text-navy">{deal.cargo_category}</MonoText>
          </div>
          <div className="sm:col-span-2">
            <p className="text-xs font-body font-medium text-muted mb-1">{t('deals.dealId')}</p>
            <MonoText className="text-xs text-muted break-all">{deal.id}</MonoText>
          </div>
        </div>

        {error && (
          <div className="px-4 sm:px-6 pb-4">
            <p className="text-xs font-mono text-amber">{error}</p>
          </div>
        )}

        <div className="px-4 sm:px-6 pb-6 flex flex-col sm:flex-row sm:flex-wrap gap-3">
          {isCarrier && deal.status === 'matched' && (
            <button
              onClick={() => handleAction('accept')}
              disabled={actionLoading}
              className="bg-cyan text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {actionLoading ? '...' : t('deals.accept')}
            </button>
          )}
          {isCarrier && deal.status === 'accepted' && (
            <button
              onClick={() => handleAction('handoff')}
              disabled={actionLoading}
              className="bg-amber text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {actionLoading ? '...' : t('deals.recordHandoff')}
            </button>
          )}
          {isSender && deal.status === 'delivered' && (
            <button
              onClick={() => handleAction('confirm')}
              disabled={actionLoading}
              className="bg-success text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {actionLoading ? '...' : t('deals.confirmReceipt')}
            </button>
          )}
          <Link
            to={`/deals/${deal.id}/vault`}
            className="border border-navy/20 text-navy font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:border-cyan transition-colors text-center"
          >
            DealVault →
          </Link>
          {isCarrier &&
            ['matched', 'accepted', 'in_transit'].includes(deal.status) && (
              <button
                onClick={() => setVerifyRequestFor('sender')}
                className="border border-cyan/40 text-link font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-cyan/10 transition-colors"
              >
                {t('verification.askSenderButton')}
              </button>
            )}
          {isSender &&
            ['matched', 'accepted', 'in_transit'].includes(deal.status) && (
              <button
                onClick={() => setVerifyRequestFor('carrier')}
                className="border border-cyan/40 text-link font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-cyan/10 transition-colors"
              >
                {t('verification.askCarrierButton')}
              </button>
            )}
          {(isCarrier || isSender) &&
            ['accepted', 'in_transit', 'delivered'].includes(deal.status) &&
            deal.status !== 'disputed' && (
              <button
                onClick={() => setDisputeOpen(true)}
                className="border border-danger/30 text-danger font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-danger/5 transition-colors"
              >
                {t('dispute.openButton')}
              </button>
            )}
        </div>
      </div>

      {disputeCreated && (
        <div className="bg-amber/10 border border-amber/40 rounded-card p-4">
          <p className="text-sm font-body text-navy">{t('dispute.createdNotice')}</p>
        </div>
      )}

      {verifySuccess && (
        <div className="bg-cyan/10 border border-cyan/40 rounded-card p-4">
          <p className="text-sm font-body text-navy">{t('verification.requestSent')}</p>
        </div>
      )}

      {openRequestForMe && !pendingRespond && (
        <div className="bg-amber/10 border border-amber/40 rounded-card p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-sm font-body text-navy">
            ⚠️ {t('verification.pendingForYou')}
          </p>
          <button
            onClick={() => setPendingRespond(openRequestForMe)}
            className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-field text-sm hover:bg-navy-mid"
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
          className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-modal flex items-center justify-center p-4"
          onClick={() => setDisputeOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-card p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <h2 className="font-display font-semibold text-lg text-navy">
              {t('dispute.modalTitle')}
            </h2>
            <p className="text-sm font-body text-muted">
              {t('dispute.modalHint')}
            </p>
            <textarea
              value={disputeReason}
              onChange={(e) => setDisputeReason(e.target.value)}
              rows={4}
              placeholder={t('dispute.reasonPlaceholder') as string}
              className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            />
            {disputeError && (
              <p className="text-xs font-mono text-danger">{disputeError}</p>
            )}
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setDisputeOpen(false)}
                className="text-sm font-body text-muted hover:text-navy px-3 py-2"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleDispute}
                disabled={disputeSubmitting || !disputeReason.trim()}
                className="bg-danger text-white font-display font-medium px-4 py-2 rounded-field text-sm hover:bg-danger/90 transition-colors disabled:opacity-40"
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
