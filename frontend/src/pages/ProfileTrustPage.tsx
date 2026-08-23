import ConnectionsSection from '../components/ConnectionsSection'
import InvitesSection from '../components/InvitesSection'
import TrustCirclesSection from '../components/TrustCirclesSection'

/**
 * T_UX.22 — «Круги доверия», in the order the graph is actually built.
 *
 * Invites and contacts come first because they are the part a person makes:
 * you send a link, somebody joins, the connection exists. The circles below are
 * what that grows into, and they read as a consequence rather than a dashboard
 * when they sit under their own cause.
 *
 * Bento sizing (DESIGNGUIDELINES §5): the two makers are 1×1 side by side and
 * equal height — `items-stretch` plus `h-full` on the cards, so a long invite
 * list does not leave the contacts card floating half-height next to it. The
 * circles are 2×1, spanning both columns, because a row of hops is a wide thing
 * and squeezing it into a half column would wrap every line.
 */
export default function ProfileTrustPage() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
      <InvitesSection />
      <ConnectionsSection />
      <div className="lg:col-span-2">
        <TrustCirclesSection />
      </div>
    </div>
  )
}
