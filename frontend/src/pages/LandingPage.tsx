import { useEffect, useRef } from 'react'
import { useReducedMotion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import MonoText from '../components/MonoText'
import Reveal from '../components/Reveal'
import LandingShell, { LandingLabel } from '../components/landing/LandingShell'

/**
 * T_UX.7 pt.2 — the landing, rebuilt in the reference's design language.
 * T_UX.23 — and now aimed at carriers first.
 *
 * **Why the root leans one way.** Supply is the precondition: a marketplace
 * with nobody flying has nothing to sell a sender, and `MASTERPLAN §4.1` says
 * so outright — free access for carriers is the cost of acquiring supply, not
 * generosity. So the hero speaks to the carrier and the second button speaks to
 * the sender, who has to see at a glance that people are already here to carry
 * for them. Two equally weighted audiences on one page would have served
 * neither.
 *
 * Both hero buttons go to the audience pages rather than opening the waitlist.
 * The full offer for either side is a page long; a modal asking for an email
 * before the offer has been read converts the people who were already sold and
 * loses everybody else. The waitlist stays one tap away in the header and at
 * the bottom of every page.
 *
 * What the shared shell owns now: header, footer, waitlist dialog, language
 * switcher, version tag. What stayed here: everything below, because it is the
 * argument this page makes and no other page makes it.
 *
 * Claims discipline (`DESIGNGUIDELINES §9.1`) is a *feature* of this page, not a
 * constraint on it: there is an explicit section for what does not exist yet,
 * and the version number is printed in the header. Nothing here says "soon",
 * because we do not have dates. Nothing counts members, because we have none to
 * count — the previous landing's investor-deck sibling did, and that number is
 * not ours to borrow.
 */

const GATES = ['post', 'match', 'handoff', 'release'] as const
const EVIDENCE = ['chain', 'identity', 'verification'] as const
const PENDING = ['payments', 'escrow', 'export'] as const

/**
 * The flight arc, restored from the original ticket
 * (`~/Downloads/Output/peerflew-offer/peerflew-investor-offer.html`, June).
 *
 * A dashed corridor with a plane travelling it is the one thing that made the
 * card read as a *ticket* rather than as a box with two airport codes in it.
 * The geometry is the original's: `M6 38 Q60 -6 114 38` in a 120×46 box, dash
 * `3 4`, navy dot at the origin and amber at the destination.
 *
 * Position comes from `getPointAtLength` and the heading from the tangent, so
 * the plane leans into the curve instead of sliding along it flat. It
 * ping-pongs rather than looping: a parcel goes there and comes back, and a
 * hard reset at the end of a loop reads as a glitch.
 *
 * Two guards, both deliberate:
 * - `useReducedMotion` — the plane is parked mid-arc instead of removed. The
 *   drawing is the point; the movement is the decoration.
 * - the effect never runs during prerender (`entry-ssr` has no DOM and no
 *   rAF), and the static markup already contains the plane, so the
 *   prerendered page is the same picture minus the motion.
 */
const FlightArc = () => {
  const reduced = useReducedMotion()
  const pathRef = useRef<SVGPathElement>(null)
  const planeRef = useRef<SVGGElement>(null)

  useEffect(() => {
    const path = pathRef.current
    const plane = planeRef.current
    if (!path || !plane || reduced) return

    const length = path.getTotalLength()
    let t = 0
    let direction = 1
    let frame = 0

    const step = () => {
      t += 0.0045 * direction
      if (t >= 1) {
        t = 1
        direction = -1
      }
      if (t <= 0) {
        t = 0
        direction = 1
      }
      const point = path.getPointAtLength(t * length)
      const ahead = path.getPointAtLength(Math.min(1, t + 0.01) * length)
      const angle = (Math.atan2(ahead.y - point.y, ahead.x - point.x) * 180) / Math.PI
      plane.setAttribute('transform', `translate(${point.x} ${point.y}) rotate(${angle})`)
      frame = requestAnimationFrame(step)
    }

    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [reduced])

  return (
    <svg
      viewBox="0 0 120 46"
      fill="none"
      className="h-[46px] w-full max-w-[160px] shrink"
      aria-hidden="true"
    >
      <path
        ref={pathRef}
        d="M6 38 Q60 -6 114 38"
        stroke="#FF7A2F"
        strokeWidth="1.6"
        strokeDasharray="3 4"
      />
      <circle cx="6" cy="38" r="3.2" fill="#0A1626" />
      <circle cx="114" cy="38" r="3.2" fill="#FF7A2F" />
      <g ref={planeRef} transform="translate(60 12) rotate(0)">
        <path d="M-5 0 L6 0 L2 -3 L8 0 L2 3 Z" fill="#0A1626" />
      </g>
    </svg>
  )
}

export default function LandingPage() {
  const { t } = useTranslation()

  return (
    <LandingShell source="landing">
      {(openWaitlist) => (
        <>
          {/* ── Hero ─────────────────────────────────────────────────────── */}
          {/* The hero is deliberately not wrapped in `Reveal`: it is on screen
              before anything can reveal it, and fading in content the visitor is
              already looking at is the motion equivalent of a splash screen. */}
          <section className="grid gap-10 border-b border-navy/10 py-14 md:grid-cols-[1.15fr_1fr] md:items-center md:py-20">
            <div>
              <LandingLabel>{t('landing.heroEyebrow')}</LandingLabel>
              <h1 className="mt-4 font-display text-[clamp(2.25rem,5.5vw,3.75rem)] font-bold leading-[1.03] tracking-[-0.03em] text-balance">
                {t('landing.heroTitle')}
              </h1>
              <p className="mt-5 max-w-[46ch] font-body text-[15px] leading-relaxed text-navy/70">
                {t('landing.heroSub')}
              </p>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                {/* Primary is the carrier. Secondary is the sender, and it is a
                    full-size button rather than a text link: the sender must
                    not feel they landed on somebody else's site. */}
                <Link
                  to="/carrier"
                  className="rounded-field bg-amber px-5 py-3 font-display text-sm font-semibold text-white transition-transform hover:brightness-95 active:translate-y-px"
                >
                  {t('landing.ctaCarrier')}
                </Link>
                <Link
                  to="/send"
                  className="rounded-field border border-navy/20 px-5 py-3 font-display text-sm font-semibold text-navy transition-colors hover:bg-navy/5"
                >
                  {t('landing.ctaSender')}
                </Link>
              </div>
            </div>

            {/* Boarding pass. Kept from the previous landing because it is the
                one image the product already owns: a parcel riding an existing
                flight is exactly what a boarding pass depicts. */}
            <div>
              {/* `relative`, and no `overflow-hidden`: the two notches below hang
                  off the card's edges, and clipping them turns a punched ticket
                  back into a rounded rectangle. */}
              <div className="relative rounded-card border border-navy/12 bg-white shadow-lift">
                {/* Stub. The dashed rule plus the two cut-outs at its ends are the
                    whole illusion — a ticket is a thing that tears. Filled with
                    the page colour so they read as holes, ringed so the edge of
                    the hole is visible against white. */}
                <div className="relative border-b-2 border-dashed border-navy/15 px-5 pb-5 pt-3">
                  <span
                    aria-hidden="true"
                    className="absolute -bottom-[11px] -left-[11px] h-[22px] w-[22px] rounded-full border border-navy/12 bg-ivory"
                  />
                  <span
                    aria-hidden="true"
                    className="absolute -bottom-[11px] -right-[11px] h-[22px] w-[22px] rounded-full border border-navy/12 bg-ivory"
                  />
                  <div className="flex items-center justify-between">
                    <MonoText className="text-[10px] uppercase tracking-[0.2em] text-navy/45">
                      {t('landing.boardingBrand')}
                    </MonoText>
                    <MonoText className="text-[10px] text-navy/35">VMN-2026-07841</MonoText>
                  </div>
                  <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
                    <div>
                      <div className="font-display text-[38px] font-bold leading-none tracking-tight">
                        DXB
                      </div>
                      <MonoText className="mt-1 text-[10px] uppercase tracking-[0.1em] text-navy/40">
                        Dubai Intl
                      </MonoText>
                    </div>
                    <FlightArc />
                    <div className="text-right">
                      <div className="font-display text-[38px] font-bold leading-none tracking-tight">
                        JFK
                      </div>
                      <MonoText className="mt-1 text-[10px] uppercase tracking-[0.1em] text-navy/40">
                        New York Kennedy
                      </MonoText>
                    </div>
                  </div>
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-5 pb-2 pt-5">
                  {[
                    ['boardingCarrier', 'Anastasia K.'],
                    ['boardingDeparts', '14 JUL · 02:35'],
                    ['boardingCargo', 'Document · 0.4 kg'],
                    ['boardingCapacity', '2.5 kg free'],
                    ['boardingEscrow', t('landing.boardingEscrowValue')],
                    ['boardingStatus', t('landing.boardingStatusValue')],
                  ].map(([key, value]) => (
                    <div key={key}>
                      <dt className="font-mono text-[10px] uppercase tracking-[0.12em] text-navy/35">
                        {t(`landing.${key}`)}
                      </dt>
                      {/* Status carries the accent and the tick, as on the
                          original: the one field of the six that is an outcome. */}
                      <dd
                        className={
                          key === 'boardingStatus'
                            ? 'mt-0.5 font-mono text-[13px] text-amber'
                            : 'mt-0.5 font-mono text-[13px] text-navy'
                        }
                      >
                        {value}
                        {key === 'boardingStatus' ? ' ✓' : ''}
                      </dd>
                    </div>
                  ))}
                </dl>
                {/* Barcode. Decoration, and honestly so — it encodes nothing.
                    Written as a gradient rather than an image so it stays sharp at
                    any width; the hex is `navy.DEFAULT`, spelled out because a
                    gradient cannot take a Tailwind colour token. */}
                <div
                  aria-hidden="true"
                  className="mx-5 mb-6 mt-3 h-[46px] rounded-[4px]"
                  style={{
                    backgroundImage:
                      'repeating-linear-gradient(90deg,#0A1626 0,#0A1626 2px,transparent 2px,transparent 4px,#0A1626 4px,#0A1626 5px,transparent 5px,transparent 9px,#0A1626 9px,#0A1626 12px,transparent 12px,transparent 14px)',
                  }}
                />
                <MonoText className="sr-only">{t('landing.boardingConfirmed')}</MonoText>
              </div>
            </div>
          </section>

          {/* ── What is true today ───────────────────────────────────────── */}
          <section className="border-b border-navy/10 py-10">
            <Reveal>
              <LandingLabel>{t('landing.factsLabel')}</LandingLabel>
              <dl className="mt-5 grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
                {['chain', 'anchors', 'key', 'corridor'].map((key, i) => (
                  <div
                    key={key}
                    className={i > 0 ? 'lg:border-l lg:border-navy/10 lg:pl-8' : undefined}
                  >
                    <dt className="font-display text-2xl font-bold tracking-tight">
                      {t(`landing.fact.${key}.value`)}
                    </dt>
                    <dd className="mt-1 font-body text-[13px] leading-snug text-navy/60">
                      {t(`landing.fact.${key}.label`)}
                    </dd>
                  </div>
                ))}
              </dl>
            </Reveal>
          </section>

          {/* ── Corridor rules ───────────────────────────────────────────
              T3.11.03 — the free half of stream D, and the one thing on this
              page a stranger can use before deciding anything. It sits above
              the problem statement on purpose: somebody who arrived holding a
              painting and a deadline is not reading an argument, they are
              looking for an answer. */}
          <section className="border-b border-navy/10 py-14">
            <Reveal>
              <LandingLabel>{t('landing.rulesLabel')}</LandingLabel>
              <h2 className="mt-4 font-display text-2xl font-bold tracking-tight md:text-3xl">
                {t('landing.rulesTitle')}
              </h2>
              <p className="mt-3 max-w-2xl font-body text-[15px] leading-relaxed text-navy/70">
                {t('landing.rulesBody')}
              </p>
              <Link
                to="/rules"
                className="mt-5 inline-block rounded-field bg-navy px-5 py-2.5 font-display text-sm font-medium text-ivory transition-opacity hover:opacity-90"
              >
                {t('landing.rulesCta')}
              </Link>
            </Reveal>
          </section>

          {/* ── Problem ──────────────────────────────────────────────────── */}
          <section className="grid gap-8 border-b border-navy/10 py-14 md:grid-cols-[0.9fr_1.1fr]">
            <Reveal>
              <LandingLabel>{t('landing.problemLabel')}</LandingLabel>
              <h2 className="mt-4 max-w-[18ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
                {t('landing.problemTitle')}
              </h2>
            </Reveal>
            <Reveal
              delay={0.08}
              className="space-y-4 font-body text-[15px] leading-relaxed text-navy/70"
            >
              <p>{t('landing.problemBody1')}</p>
              <p>{t('landing.problemBody2')}</p>
            </Reveal>
          </section>

          {/* ── Four gates ───────────────────────────────────────────────── */}
          <section className="border-b border-navy/10 py-14">
            <Reveal>
              <LandingLabel>{t('landing.gatesLabel')}</LandingLabel>
              <h2 className="mt-4 max-w-[22ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
                {t('landing.gatesTitle')}
              </h2>
            </Reveal>
            <ol className="mt-9 grid gap-px overflow-hidden rounded-card border border-navy/10 bg-navy/10 sm:grid-cols-2 lg:grid-cols-4">
              {GATES.map((gate, i) => (
                <Reveal key={gate} as="li" delay={i * 0.06} className="bg-ivory h-full p-6">
                  <div>
                    <MonoText className="text-[13px] font-medium text-amber">
                      {String(i + 1).padStart(2, '0')}
                    </MonoText>
                    <h3 className="mt-3 font-display text-lg font-semibold tracking-tight">
                      {t(`landing.gate.${gate}.title`)}
                    </h3>
                    <p className="mt-2 font-body text-[13.5px] leading-relaxed text-navy/65">
                      {t(`landing.gate.${gate}.body`)}
                    </p>
                  </div>
                </Reveal>
              ))}
            </ol>
          </section>

          {/* ── What holds it together ───────────────────────────────────── */}
          <section className="border-b border-navy/10 py-14">
            <Reveal>
              <LandingLabel>{t('landing.evidenceLabel')}</LandingLabel>
              <h2 className="mt-4 max-w-[24ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
                {t('landing.evidenceTitle')}
              </h2>
            </Reveal>
            <div className="mt-9 space-y-px overflow-hidden rounded-card border border-navy/10 bg-navy/10">
              {EVIDENCE.map((item, i) => (
                <Reveal key={item} delay={i * 0.06} className="bg-white">
                  <article className="grid gap-3 p-6 md:grid-cols-[0.8fr_1.2fr] md:gap-8">
                    <h3 className="font-display text-lg font-semibold tracking-tight">
                      {t(`landing.evidence.${item}.title`)}
                    </h3>
                    <div className="space-y-2">
                      <p className="font-body text-[14px] leading-relaxed text-navy/70">
                        {t(`landing.evidence.${item}.body`)}
                      </p>
                      {/* The limit of the claim, printed next to the claim. This
                          is the §9.1 rule made visible rather than obeyed
                          quietly: a reader who only skims the bold line still
                          cannot come away with more than the mechanism gives. */}
                      <MonoText className="block text-[11.5px] leading-relaxed text-navy/45">
                        {t(`landing.evidence.${item}.limit`)}
                      </MonoText>
                    </div>
                  </article>
                </Reveal>
              ))}
            </div>
          </section>

          {/* ── Not built yet ────────────────────────────────────────────── */}
          <section className="border-b border-navy/10 py-14">
            <Reveal>
              <LandingLabel>{t('landing.pendingLabel')}</LandingLabel>
              <h2 className="mt-4 max-w-[20ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
                {t('landing.pendingTitle')}
              </h2>
              <p className="mt-4 max-w-[54ch] font-body text-[15px] leading-relaxed text-navy/70">
                {t('landing.pendingBody')}
              </p>
            </Reveal>
            <ul className="mt-8 grid gap-4 sm:grid-cols-3">
              {PENDING.map((item, i) => (
                <Reveal
                  key={item}
                  as="li"
                  delay={i * 0.06}
                  className="h-full rounded-card border border-dashed border-navy/20 p-5"
                >
                  <div>
                    <MonoText className="text-[11px] uppercase tracking-[0.14em] text-navy/35">
                      {t('landing.pendingTag')}
                    </MonoText>
                    <h3 className="mt-2.5 font-display text-base font-semibold tracking-tight text-navy/80">
                      {t(`landing.pending.${item}.title`)}
                    </h3>
                    <p className="mt-1.5 font-body text-[13px] leading-relaxed text-navy/55">
                      {t(`landing.pending.${item}.body`)}
                    </p>
                  </div>
                </Reveal>
              ))}
            </ul>
          </section>

          {/* ── Closing ──────────────────────────────────────────────────── */}
          <section className="py-16">
            <Reveal className="rounded-card border border-navy/12 bg-navy px-7 py-10 text-ivory md:px-12 md:py-14">
              <MonoText className="text-[11px] uppercase tracking-[0.16em] text-ivory/45">
                {t('landing.closingLabel')}
              </MonoText>
              <h2 className="mt-4 max-w-[20ch] font-display text-[clamp(1.6rem,3.4vw,2.5rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
                {t('landing.closingTitle')}
              </h2>
              <p className="mt-4 max-w-[48ch] font-body text-[15px] leading-relaxed text-ivory/70">
                {t('landing.closingBody')}
              </p>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={openWaitlist}
                  className="rounded-field bg-amber px-5 py-3 font-display text-sm font-semibold text-white transition-transform hover:brightness-95 active:translate-y-px"
                >
                  {t('landing.ctaInvite')}
                </button>
                <Link
                  to="/login"
                  className="rounded-field border border-ivory/25 px-5 py-3 font-display text-sm font-semibold text-ivory transition-colors hover:bg-ivory/10"
                >
                  {t('landing.ctaLogin')}
                </Link>
              </div>
            </Reveal>
          </section>
        </>
      )}
    </LandingShell>
  )
}
