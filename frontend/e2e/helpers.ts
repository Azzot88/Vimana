import { type Page } from '@playwright/test'

/**
 * E2E helpers — signing in as one of the long-lived accounts.
 *
 * There used to be a `registerUser` here that drove the sign-up form. That form
 * stopped existing on 2026-08-10: T3.28 reduced sign-in and sign-up to one
 * field plus a mailed code, and `/register` became a redirect to `/login`. A
 * test cannot read the code, so it cannot create an account at all.
 *
 * It survived twelve days because the suite is run by hand — "broken" and "not
 * run lately" look identical from outside. Removed in T_TEST.12 rather than
 * repaired: there is nothing to repair, the flow it drove is gone.
 *
 * **Authentication happens through the API, not the form.** What broke was a
 * test driving a UI it was not testing, and setup should not depend on markup
 * that belongs to somebody else's feature. The login *screen* still gets
 * covered — by the specs that are actually about signing in.
 *
 * Account setup is in README.md. The password has to be set **on the account**,
 * through the product's own step-up, because sign-up by code creates none.
 */

export interface SignInOpts {
  /** Set `active_mode` after signing in. The panel and the nav differ by mode,
   *  so a spec that means "as a carrier" has to say so. */
  mode?: 'carrier' | 'sender'
  /** Which long-lived account. `second` exists for the one thing a single
   *  account cannot do — be two people at once. An invite has to be accepted by
   *  somebody other than its author. */
  as?: 'primary' | 'second'
}

export interface SignedIn {
  email: string
  password: string
  token: string
  displayName: string
}

export async function signInFixed(
  page: Page,
  opts: SignInOpts = {},
): Promise<SignedIn> {
  const second = opts.as === 'second'
  const names = second ? 'E2E_USER2 / E2E_PASSWORD2' : 'E2E_USER / E2E_PASSWORD'
  const email = second ? process.env.E2E_USER2 : process.env.E2E_USER
  const password = second ? process.env.E2E_PASSWORD2 : process.env.E2E_PASSWORD

  if (!email || !password) {
    throw new Error(
      `${names} are not set. The suite signs in as long-lived accounts ` +
        "(owner's decision 2026-08-22): registration through the UI is " +
        'code-based since T3.28 and cannot be automated. See e2e/README.md.',
    )
  }

  const res = await page.request.post('/api/auth/login', {
    data: { login: email, password },
  })
  if (!res.ok()) {
    // A 401 here means one of two things and the API deliberately does not say
    // which — it must not reveal whether an address exists. The hint belongs on
    // this side, where both possibilities are known: an account registered by
    // code has **no password at all** until one is set, and `/login` refuses a
    // null hash exactly the way it refuses a wrong one.
    const hint =
      res.status() === 401
        ? '\n  Either the password is wrong, or this account has none: sign-up ' +
          'by code does not create one. See e2e/README.md.'
        : ''
    throw new Error(
      `login failed for ${email}: ${res.status()} ${await res.text()}${hint}`,
    )
  }
  const { access_token: token } = (await res.json()) as { access_token: string }

  // Origin first: `localStorage` belongs to one, and setting it before any
  // navigation writes it into `about:blank`.
  await page.goto('/')
  await page.evaluate((t) => localStorage.setItem('token', t), token)

  const auth = { Authorization: `Bearer ${token}` }

  if (opts.mode) {
    const patch = await page.request.patch('/api/auth/me', {
      data: { active_mode: opts.mode },
      headers: auth,
    })
    if (!patch.ok()) {
      throw new Error(`could not switch to ${opts.mode}: ${patch.status()}`)
    }
  }

  // Read rather than assume. The display name belongs to the account, and the
  // one spec that asserts on it must not carry its own copy to drift the day
  // somebody renames the account from the profile screen.
  const me = await page.request.get('/api/auth/me', { headers: auth })
  if (!me.ok()) {
    throw new Error(`GET /api/auth/me failed: ${me.status()} ${await me.text()}`)
  }
  const { display_name: displayName } = (await me.json()) as {
    display_name: string
  }

  return { email, password, token, displayName }
}

/**
 * T_TEST.12 — leave the account with no passkeys.
 *
 * Registered credentials live on the server, and the virtual authenticator does
 * not know that: it is created fresh per test, so every run adds a credential
 * and none of them ever leaves. With a throwaway account that was invisible —
 * with a shared one, the second run finds two where the spec asserts one, and
 * the failure reads as a WebAuthn regression.
 *
 * Removal needs step-up, the same as it does in the interface, so this walks
 * the real endpoints: confirm with the password, then delete with the grant in
 * a header. A fresh grant per credential because the token is scoped to one
 * operation and cheap to reissue.
 *
 * Safe only because these accounts have a password: the server refuses to
 * remove the last way in, and it is right to.
 */
export async function clearPasskeys(page: Page, signedIn: SignedIn) {
  const auth = { Authorization: `Bearer ${signedIn.token}` }

  const listed = await page.request.get('/api/auth/passkey/', { headers: auth })
  if (!listed.ok()) {
    throw new Error(`could not list passkeys: ${listed.status()}`)
  }
  const credentials = (await listed.json()) as Array<{ id: string }>

  for (const credential of credentials) {
    const stepUp = await page.request.post('/api/auth/step-up/verify', {
      data: { scope: 'unlink_passkey', password: signedIn.password },
      headers: auth,
    })
    if (!stepUp.ok()) {
      throw new Error(
        `step-up for unlink_passkey failed: ${stepUp.status()} ${await stepUp.text()}`,
      )
    }
    const { step_up_token: grant } = (await stepUp.json()) as {
      step_up_token: string
    }

    const removed = await page.request.delete(`/api/auth/passkey/${credential.id}`, {
      headers: { ...auth, 'X-Step-Up-Token': grant },
    })
    if (!removed.ok()) {
      throw new Error(
        `could not remove passkey ${credential.id}: ${removed.status()} ${await removed.text()}`,
      )
    }
  }
}
