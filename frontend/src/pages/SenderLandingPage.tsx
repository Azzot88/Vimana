import AudienceLanding from '../components/landing/AudienceLanding'

/** T_UX.23 — `/send` for a visitor without a session.
 *
 *  A signed-in account never reaches this: `ModeHomePage` sends it to the panel
 *  instead. One address, two screens — see the note there. */
export default function SenderLandingPage() {
  return <AudienceLanding audience="sender" secondaryTo="/carrier" />
}
