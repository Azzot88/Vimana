import MonoText from '../MonoText'

/**
 * T_UX.23 — the one picture each audience page is built around.
 *
 * The brief asks for a different "main visual object" per audience — for a
 * carrier `route → free space → request → money`, for a sender
 * `from → to → parcel → search`. They are the same object with different words
 * in it, and that is exactly the 70/30 split the split is supposed to have:
 * one shape everywhere, different content inside.
 *
 * Deliberately typographic rather than illustrated. The product has no
 * photography and no illustration set, and inventing one for three pages would
 * make them look like a different company from the app they lead into — the
 * failure `T_UX.7` spent a whole task undoing. Mono type in boxes is the
 * departure-board language the rest of the product already speaks.
 *
 * The last step carries the accent because it is the outcome: money for the
 * carrier, a found carrier for the sender, a delivered order for a business.
 */
export default function FlowStrip({ steps }: { steps: string[] }) {
  return (
    <ol className="flex flex-wrap items-stretch gap-2" aria-label={steps.join(' → ')}>
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1
        return (
          <li key={step} className="flex items-stretch gap-2">
            <div
              className={`flex min-h-[52px] flex-1 items-center rounded-field border px-3.5 py-2.5 ${
                isLast
                  ? 'border-amber/40 bg-amber/5'
                  : 'border-navy/12 bg-white'
              }`}
            >
              <div>
                <MonoText className="block text-[10px] uppercase tracking-[0.16em] text-navy/35">
                  {String(i + 1).padStart(2, '0')}
                </MonoText>
                <span
                  className={`mt-0.5 block font-display text-[13.5px] font-semibold leading-tight ${
                    isLast ? 'text-amber' : 'text-navy'
                  }`}
                >
                  {step}
                </span>
              </div>
            </div>
            {!isLast && (
              <span
                aria-hidden="true"
                className="self-center font-mono text-navy/25"
              >
                →
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}
