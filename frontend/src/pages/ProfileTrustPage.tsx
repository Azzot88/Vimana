import ConnectionsSection from '../components/ConnectionsSection'
import InvitesSection from '../components/InvitesSection'
import TrustCirclesSection from '../components/TrustCirclesSection'

/**
 * T_UX.20 — «Круги доверия».
 *
 * Three views of one thing, which is why they were worth collecting: the graph
 * outward (circles by hop), the graph as names (connections), and the way it
 * gets one person wider (invites). On the old profile the invite list sat four
 * cards below the circles, in the other column.
 */
export default function ProfileTrustPage() {
  return (
    <div className="space-y-4">
      <TrustCirclesSection />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <ConnectionsSection />
        <InvitesSection />
      </div>
    </div>
  )
}
