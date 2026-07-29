"""T3.14 — WebAuthn ceremonies.

`py_webauthn` does the hard parts: CBOR/COSE parsing, attestation, signature
verification. What lives here is our side of it — ceremony state, the rules we
chose, and the reasons for them.

Challenges reuse `core/challenge.py` (Redis, one-shot `GETDEL`), the same store
`establish` and Nostr login use. Same reason it refuses rather than fails soft:
a challenge we cannot verify we issued is a challenge we must not accept.

**RP ID and origin have to be right or nothing works, silently.** The browser
checks both before it talks to us — a mismatch aborts the ceremony on its side
and the server never sees a request. If passkeys "do nothing" with no log
entry, check these two settings first.
"""
from __future__ import annotations

import logging

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# Scopes for `core.challenge`. Separate per ceremony so a challenge minted for
# registration cannot be spent on a login.
SCOPE_REGISTER = "webauthn:register"
SCOPE_LOGIN = "webauthn:login"
SCOPE_SIGNUP = "webauthn:signup"

# Sentinel subject for ceremonies that have no user yet (login is usernameless,
# signup has no account). The challenge is still one-shot per subject; these two
# flows are rate-limited at the endpoint instead.
ANONYMOUS = "anonymous"


def registration_options(
    *,
    user_id_bytes: bytes,
    user_name: str,
    display_name: str,
    exclude_credential_ids: list[bytes],
) -> tuple[str, bytes]:
    """Returns (options JSON, challenge bytes).

    `resident_key=REQUIRED` is what makes usernameless login possible at all:
    the credential is stored on the authenticator with the user handle inside,
    so the browser can offer it without being told which account to look for.

    `user_verification=PREFERRED`, not REQUIRED — REQUIRED turns away
    authenticators with no PIN or biometric, which is a real share of hardware
    keys. We record what actually happened in `uv_capable` instead, so step-up
    (T3.15) can demand verified presence later without locking anyone out now.
    """
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=user_id_bytes,
        user_name=user_name,
        user_display_name=display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        # Stops a device that is already registered from being added twice —
        # the browser greys it out instead of producing a duplicate.
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=cid) for cid in exclude_credential_ids
        ],
    )
    return options_to_json(options), options.challenge


def authentication_options() -> tuple[str, bytes]:
    """Login options with an **empty** `allowCredentials`.

    Deliberate: naming the acceptable credentials would mean knowing who is
    logging in before they prove it, which turns the endpoint into an oracle
    for "does this account exist". Empty means the browser offers whatever
    discoverable credential it holds for this site.
    """
    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return options_to_json(options), options.challenge


def verify_registration(*, credential: dict, expected_challenge: bytes):
    """Raises `webauthn.helpers.exceptions.InvalidRegistrationResponse` on any
    failure — the caller maps that to 401."""
    return verify_registration_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=settings.WEBAUTHN_RP_ID,
        expected_origin=settings.WEBAUTHN_ORIGIN,
    )


def verify_authentication(
    *,
    credential: dict,
    expected_challenge: bytes,
    public_key: bytes,
    current_sign_count: int,
):
    """Raises `InvalidAuthenticationResponse` on failure.

    `require_user_verification=False` mirrors the PREFERRED policy above.
    """
    return verify_authentication_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=settings.WEBAUTHN_RP_ID,
        expected_origin=settings.WEBAUTHN_ORIGIN,
        credential_public_key=public_key,
        credential_current_sign_count=current_sign_count,
        require_user_verification=False,
    )


def sign_count_is_acceptable(stored: int, presented: int) -> bool:
    """The clone check — with the exception that makes it usable.

    A counter that goes backwards suggests two authenticators sharing one
    credential, i.e. a clone. But **synced passkeys report 0 forever**: iCloud
    Keychain and Google Password Manager copy credentials between devices by
    design, so a counter would be meaningless and they do not keep one.

    Enforcing `presented > stored` unconditionally would therefore reject the
    most common passkey in existence on its second use. So: while the stored
    count is 0 we accept anything, and only once an authenticator has proven it
    keeps a real counter do we hold it to that.
    """
    if stored == 0:
        return True
    return presented > stored


def remaining_ways_in(user, credential_count: int) -> int:
    """How many ways this account could still be signed into.

    Counts what actually authenticates: a password, an identity key the user
    holds (Nostr login, T3.13), and each registered passkey. Email is not one —
    it confirms an address, it does not sign anyone in.
    """
    ways = credential_count
    if user.password_hash:
        ways += 1
    if user.key_self_custody and user.key_lost_at is None:
        ways += 1
    return ways


def would_lock_the_user_out(user, credential_count: int) -> bool:
    """True if deleting one passkey leaves no way back in.

    Worth being strict about: email is optional in this product, so there may
    be no address to recover through, and a passwordless account with one
    passkey has exactly one door. Removing it is not "logging out" — it is
    losing the account, with nothing on our side able to undo it.
    """
    return remaining_ways_in(user, credential_count) <= 1


def describe_device(*, transports: list[str] | None, backed_up: bool) -> str:
    """Short label for the login-devices list.

    A hardware key that lives on exactly one device and a credential synced
    across a whole account are different things to lose, so the UI says which
    is which.
    """
    t = set(transports or [])
    if not backed_up and t & {"usb", "nfc"}:
        return "hardware_key"
    if backed_up:
        return "synced_passkey"
    return "device_passkey"
