import { useTranslation } from 'react-i18next'

/**
 * The one field a six-digit code is typed into.
 *
 * Extracted 2026-08-10 after the sign-in screen grew a second one with its own
 * border, its own button and its own place on the page — next to the existing
 * field on the confirmation screen it read as a different product. Two inputs
 * that ask for the same thing must not look like two different things, and the
 * way to guarantee that is to have one of them.
 *
 * The mono face and the wide tracking are not decoration: they come from the
 * departure-board metaphor in DESIGNGUIDELINES, and the same treatment is used
 * for the code plaque inside the letter that delivers it. Someone copying six
 * digits from a message into a form should recognise the second thing from the
 * first.
 *
 * Digits only, six of them, filtered on the way in — pasting a code with a
 * space or a stray letter is normal, and rejecting it afterwards would blame
 * the person for their mail client.
 *
 * Called by: `pages/LoginPage`, `pages/VerifyEmailPage`.
 */
interface Props {
  value: string
  onChange: (value: string) => void
  id?: string
  label?: string
  autoFocus?: boolean
  'data-testid'?: string
}

export default function CodeField({
  value,
  onChange,
  id = 'code',
  label,
  autoFocus,
  ...rest
}: Props) {
  const { t } = useTranslation()
  return (
    <div>
      <label
        htmlFor={id}
        className={
          label
            ? 'block text-xs font-body font-medium text-navy/60 mb-1'
            : 'sr-only'
        }
      >
        {label ?? t('auth.code')}
      </label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
        inputMode="numeric"
        autoComplete="one-time-code"
        autoFocus={autoFocus}
        placeholder="000000"
        data-testid={rest['data-testid']}
        className="w-full border border-navy/20 rounded-field px-3 py-2 font-mono text-lg tracking-[0.4em] text-navy text-center focus:outline-none focus:border-cyan transition-colors"
      />
    </div>
  )
}
