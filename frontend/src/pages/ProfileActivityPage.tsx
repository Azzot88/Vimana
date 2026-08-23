import UBASection from '../components/UBASection'
import VerificationSection from '../components/VerificationSection'

/**
 * T_UX.20 — «Уровень активности».
 *
 * Verification sits with the number rather than with the keys, and that is not
 * a filing preference: `Vrf` is a multiplier inside the УБА formula itself
 * (IMPLEMENTATIONPLAN §3.1, `null→1.00 / auto→1.05 / peer→1.15 / kyc→1.30`).
 * Putting the badges anywhere else would separate a component of the score from
 * the score it moves.
 *
 * The section is not called "репутация" anywhere. `D3` was taken directly
 * against that word — the metric is business activity, measured in deeds,
 * precisely because it is harder to inflate than reviews.
 */
export default function ProfileActivityPage() {
  return (
    <div className="space-y-4">
      <UBASection />
      <VerificationSection />
    </div>
  )
}
