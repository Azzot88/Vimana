/**
 * T_UX.30 — where a person goes after proving who they are, decided in one place.
 *
 * Before this module the answer lived in six files and they disagreed: a code or
 * a password landed on the public front page, a passkey or a Nostr signature on
 * the panel, a new account on `/welcome` and then the panel whatever it had come
 * for. The invite page spelled the parameter `returnUrl`, the recipient's link
 * spelled it `next`, and the sign-in page read only the first — so a stranger
 * following a recipient link signed up and never saw the offer
 * (`D-USER-PATHS`, ревизия путей R2).
 *
 * One parameter name, one fallback, one validator.
 *
 * Functions (PROJECT §6.2a):
 * - `safeReturnUrl(raw)` — an in-app path or the panel. Called by: `LoginPage`,
 *   `WelcomePage`, `VerifyEmailPage`, `withReturn`.
 * - `withReturn(path, back)` — `path` carrying `back` as `?returnUrl=`, or bare
 *   when there is nowhere special to return to. Called by: `ProtectedRoute`,
 *   `JoinDealPage`, `AcceptInvitePage`, `afterSignIn`.
 * - `afterSignIn(returnUrl, facts)` — the first screen after a successful sign-in.
 *   Called by: `LoginPage`, `PasskeyAuthButton`, `NostrAuthButton`.
 */

/** The panel: the one screen that is about the person who just signed in. The
 *  front page is a pitch to somebody who has not, and landing there after a
 *  code was one click of ceremony in front of «Открыть кабинет». */
export const AFTER_SIGN_IN = '/dashboard'

/**
 * T_UX.7 pt.2 — the destination is attacker-reachable through the query string,
 * which is precisely what the react-router open-redirect advisory
 * (GHSA-wrjc-x8rr-h8h6) turns into an off-site redirect. So the check is narrow
 * rather than clever: one leading slash, no scheme, no protocol-relative `//`, no
 * backslash — which browsers normalise to `/`. Anything else falls back to the
 * panel: a sign-in that lands somewhere harmless is a nuisance, one that lands
 * on an attacker's page is a phishing step.
 */
export function safeReturnUrl(raw: string | null | undefined): string {
  if (!raw) return AFTER_SIGN_IN
  if (!raw.startsWith('/')) return AFTER_SIGN_IN
  if (raw.startsWith('//') || raw.startsWith('/\\')) return AFTER_SIGN_IN
  if (raw.includes('\\')) return AFTER_SIGN_IN
  return raw
}

/** `path?returnUrl=<back>`, validated on the way out as well as on the way in.
 *  The panel is not carried: it is where everybody goes anyway, and a parameter
 *  that says nothing is noise in every address bar it passes through. */
export function withReturn(path: string, back: string | null | undefined): string {
  const target = safeReturnUrl(back)
  if (target === AFTER_SIGN_IN) return path
  const joiner = path.includes('?') ? '&' : '?'
  return `${path}${joiner}returnUrl=${encodeURIComponent(target)}`
}

/** The first screen after a sign-in. A new account names itself first, an
 *  unconfirmed address is confirmed first — and both of those screens carry the
 *  destination on, so the person still ends up where they pressed. */
export function afterSignIn(
  returnUrl: string,
  { created = false, emailUnverified = false }: { created?: boolean; emailUnverified?: boolean } = {},
): string {
  if (created) return withReturn('/welcome', returnUrl)
  if (emailUnverified) return withReturn('/verify-email', returnUrl)
  return safeReturnUrl(returnUrl)
}
