import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, Link } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { usePrefs } from '../hooks/usePrefs'
import { openDispute } from '../api/admin'
import { getDeal, type DealDetail } from '../api/deals'
import { listDealRequests, type VerificationRequest as VerificationRequestT } from '../api/verification'
import { listParticipants, type Participant } from '../api/participants'
import AddContactButton from '../components/AddContactButton'
import StatusBadge from '../components/StatusBadge'
import MonoText from '../components/MonoText'
import PlatformNoticeBanner from '../components/PlatformNoticeBanner'
import RouteNoteBadge from '../components/RouteNoteBadge'
import VerificationDeclineBanner from '../components/VerificationDeclineBanner'
import VerificationRequestModal from '../components/VerificationRequestModal'
import VerificationRespondModal from '../components/VerificationRespondModal'
import { useRouteNotes } from '../hooks/useRouteNotes'

/** T3.11.26 — the deal card, now shown **inside** the vault rather than in
 *  front of it (owner's decision 2026-09-07).
 *
 *  It stopped being a route: `/deals/:id` redirects into the conversation,
 *  because a screen whose only purpose is to be clicked through is a screen.
 *  What was on it is not ceremony though — the boarding pass, the terms, the
 *  verification and the dispute button are the deal — so it moved rather than
 *  went. `embedded` is the difference between the two homes: no back-link (the
 *  vault has one) and no page width of its own (it sits inside a panel).
 *
 *  Called by: `pages/DealVaultPage`, folded into a `<details>` under the header.
 */
export default function DealPage({ embedded = false }: { embedded?: boolean }) {
  const prefs = usePrefs()
  const { t } = useTranslation()
  const { dealId } = useParams<{ dealId: string }>()
  const user = useAuthStore((s) => s.user)
  const [deal, setDeal] = useState<DealDetail | null>(null)
  const [loading, setLoading] = useState(true)
  // T_UX.2 pt.3 — RouteNotes for this corridor (empty until deal loads).
  const { notes: routeNotes } = useRouteNotes(deal?.origin, deal?.destination)
  const [error, setError] = useState('')
  const [disputeOpen, setDisputeOpen] = useState(false)
  const [disputeReason, setDisputeReason] = useState('')
  const [disputeSubmitting, setDisputeSubmitting] = useState(false)
  const [disputeError, setDisputeError] = useState('')
  const [disputeCreated, setDisputeCreated] = useState(false)
  const [verifyRequestFor, setVerifyRequestFor] = useState<'sender' | 'carrier' | null>(null)
  const [pendingRespond, setPendingRespond] = useState<VerificationRequestT | null>(null)
  const [verifySuccess, setVerifySuccess] = useState(false)
  const [participants, setParticipants] = useState<Participant[]>([])

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

  /* T3.11.24 — who else is on this deal. Its own request rather than a field on
     the deal: participants change without the deal changing, and folding them
     into the detail response would mean re-reading a whole deal to learn that
     one recipient accepted. Failure costs the list, not the page. */
  useEffect(() => {
    if (!dealId) return
    listParticipants(dealId)
      .then(({ data }) => setParticipants(data))
      .catch(() => setParticipants([]))
  }, [dealId])


  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-navy/40 text-sm">{t('common.loading')}</MonoText>
      </div>
    )
  }

  if (!deal) {
    return (
      <div className="text-center py-24">
        <p className="text-sm font-body text-navy/40">{error || t('deals.notFound')}</p>
      </div>
    )
  }

  const isCarrier = deal.carrier_id === user?.id
  const isSender = deal.sender_id === user?.id

  return (
    <div className={embedded ? 'space-y-6' : 'max-w-2xl space-y-6'}>
      {!embedded && (
        <div className="flex items-center gap-3">
          <Link
            to="/deals"
            className="text-xs font-body text-navy/40 hover:text-navy transition-colors"
          >
            ← {t('nav.deals')}
          </Link>
        </div>
      )}

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
              <p className="text-xs font-mono text-white/40 uppercase tracking-widest">{t('deals.boardingPass')}</p>
              <MonoText className="text-xl text-white font-medium">
                {deal.origin} → {deal.destination}
              </MonoText>
              <MonoText className="text-sm text-white/60">
                {prefs.dateTime(deal.depart_at)}
              </MonoText>
            </div>
            <div className="self-start"><StatusBadge status={deal.status} /></div>
          </div>
        </div>

        <div className="p-4 sm:p-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* T3.11.24 — the deal's participants are the other place «добавить в
              контакты» belongs: this is where you have just dealt with somebody
              and know whether you would deal with them again. The button draws
              nothing for yourself, so each side sees exactly one. */}
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">{t('deals.sender')}</p>
            <div className="flex items-center gap-2">
              <p className="text-sm font-body text-navy font-medium">{deal.sender_name}</p>
              <AddContactButton userId={deal.sender_id} inline />
            </div>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">{t('deals.carrier')}</p>
            <div className="flex items-center gap-2">
              <Link
                to={`/carriers/${deal.carrier_id}`}
                className="text-sm font-body text-navy font-medium hover:text-cyan transition-colors underline decoration-navy/20 underline-offset-2"
              >
                {deal.carrier_name}
              </Link>
              <AddContactButton userId={deal.carrier_id} inline />
            </div>
          </div>
          {/* The recipients, when there are any. Until now this list existed on
              the server and nowhere on screen: a deal could have a third person
              reading it and neither principal could see who. */}
          {participants.length > 0 && (
            <div className="sm:col-span-2">
              <p className="text-xs font-body font-medium text-navy/40 mb-1">
                {t('deals.recipients')}
              </p>
              <div className="space-y-1">
                {participants.map((p) => (
                  <div key={p.id} className="flex items-center gap-2">
                    <p className="text-sm font-body text-navy">
                      {p.display_name ?? t('recipient.pendingInvite')}
                    </p>
                    {p.accepted_at === null && (
                      <span className="text-[10px] font-mono uppercase bg-navy/5 text-navy/50 px-1.5 py-0.5 rounded">
                        {t('recipient.pendingInvite')}
                      </span>
                    )}
                    {p.user_id && <AddContactButton userId={p.user_id} inline />}
                  </div>
                ))}
              </div>
            </div>
          )}
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">{t('deals.cargo')}</p>
            <p className="text-sm font-body text-navy">{deal.cargo_description}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">{t('deals.category')}</p>
            <MonoText className="text-sm text-navy">{deal.cargo_category}</MonoText>
          </div>
          {deal.carriage_rules && (
            <div className="sm:col-span-2">
              <p className="text-xs font-body font-medium text-navy/40 mb-1">
                {t('deals.carriageRules')}
              </p>
              {/* T_UX.15 — what the sender agreed to when they chose this trip.
                  Shown in full rather than behind a link: rules nobody reads are
                  rules nobody agreed to. */}
              <p className="text-sm font-body text-navy whitespace-pre-wrap">
                {deal.carriage_rules}
              </p>
            </div>
          )}
          {/* T3.11.23 — the shipment number stands above the UUID and in a
              readable size: it is the one identifier that gets dictated on the
              phone and pasted into a message. The UUID stays for support, where
              exactness beats speakability. */}
          {deal.shipment_no && (
            <div>
              <p className="text-xs font-body font-medium text-navy/40 mb-1">
                {t('deals.shipmentNo')}
              </p>
              <MonoText className="text-sm text-navy tracking-wide">
                {deal.shipment_no}
              </MonoText>
            </div>
          )}
          <div className="sm:col-span-2">
            <p className="text-xs font-body font-medium text-navy/40 mb-1">{t('deals.dealId')}</p>
            <MonoText className="text-xs text-navy/50 break-all">{deal.id}</MonoText>
          </div>
        </div>

        {error && (
          <div className="px-4 sm:px-6 pb-4">
            <p className="text-xs font-mono text-amber">{error}</p>
          </div>
        )}

        <div className="px-4 sm:px-6 pb-6 flex flex-col sm:flex-row sm:flex-wrap gap-3">
          {/* T3.11.17 — three buttons left this row (owner's decision
              2026-09-07). «Согласовать условия» and «DealVault →» were links to
              the screen this card is now drawn on, and «Зафиксировать передачу»
              was a second route to a status the handover card already reaches —
              with the difference that it skipped the photograph and the other
              side's confirmation. What the deal *does* now lives on the stage
              panel, in one place, in the order it happens. What is left here is
              what belongs to the card rather than to the step: asking the other
              side for a document, and opening a dispute. */}
          {isCarrier &&
            ['matched', 'accepted', 'in_transit'].includes(deal.status) && (
              <button
                onClick={() => setVerifyRequestFor('sender')}
                className="border border-cyan/40 text-cyan font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-cyan/10 transition-colors"
              >
                {t('verification.askSenderButton')}
              </button>
            )}
          {isSender &&
            ['matched', 'accepted', 'in_transit'].includes(deal.status) && (
              <button
                onClick={() => setVerifyRequestFor('carrier')}
                className="border border-cyan/40 text-cyan font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-cyan/10 transition-colors"
              >
                {t('verification.askCarrierButton')}
              </button>
            )}
          {(isCarrier || isSender) &&
            /* T3.11.17 — a parcel in the post is exactly when a dispute becomes
               likely, so `posted` is in this list. */
            ['accepted', 'in_transit', 'posted', 'delivered'].includes(
              deal.status,
            ) &&
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
            <p className="text-sm font-body text-navy/60">
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
                className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2"
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
