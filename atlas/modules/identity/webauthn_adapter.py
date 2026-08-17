"""WebAuthn passkey ceremonies.

Blueprint §15: passkeys, registered devices, owner-approved enrollment. This
wraps ``py_webauthn`` so the ceremony details stay in one place and the service
layer deals in decisions rather than in CBOR.

Private to this module — a caller outside Identity must not be able to verify
its own assertion.

The signature-counter check below is the part worth reading. WebAuthn
authenticators increment a counter on every assertion; a counter that fails to
advance is the specification's signal that a credential has been cloned, since
two copies of the same key cannot both keep counting upwards. ``schema.sql``
had no column for it at all, so this check was impossible until
``identity.devices.sign_counter`` was added.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    options_to_json,
    parse_authentication_credential_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from atlas.modules.identity.contracts import WebAuthnError
from atlas.modules.identity.schemas import RelyingParty


class ClonedAuthenticatorError(WebAuthnError):
    """Raised when the signature counter does not advance.

    Treated as a security incident rather than a login failure: the credential
    should be revoked and the owner notified, because the plausible
    explanations are a cloned authenticator or a replayed assertion.
    """

    def __init__(self, *, stored: int, presented: int) -> None:
        super().__init__(
            f"signature counter did not advance (stored={stored}, "
            f"presented={presented}); credential may have been cloned"
        )
        self.stored = stored
        self.presented = presented


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    credential_id: str
    public_key: str
    sign_count: int


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    credential_id: str
    sign_count: int


def registration_options(
    *, rp: RelyingParty, user_id: bytes, user_name: str, user_display_name: str
) -> tuple[bytes, dict[str, Any]]:
    options = generate_registration_options(
        rp_id=rp.rp_id,
        rp_name=rp.rp_name,
        user_id=user_id,
        user_name=user_name,
        user_display_name=user_display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    return options.challenge, json.loads(options_to_json(options))


def verify_registration(
    *, rp: RelyingParty, expected_challenge: bytes, credential: dict[str, Any]
) -> RegistrationResult:
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=rp.origin,
            require_user_verification=True,
        )
    except Exception as exc:
        raise WebAuthnError("registration verification failed") from exc
    return RegistrationResult(
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=bytes_to_base64url(verified.credential_public_key),
        sign_count=verified.sign_count,
    )


def authentication_options(*, rp: RelyingParty) -> tuple[bytes, dict[str, Any]]:
    options = generate_authentication_options(
        rp_id=rp.rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return options.challenge, json.loads(options_to_json(options))


def credential_id_from_authentication(credential: dict[str, Any]) -> str:
    try:
        parsed = parse_authentication_credential_json(credential)
    except Exception as exc:
        raise WebAuthnError("authentication credential is malformed") from exc
    return bytes_to_base64url(parsed.raw_id)


def verify_authentication(
    *,
    rp: RelyingParty,
    expected_challenge: bytes,
    credential: dict[str, Any],
    credential_public_key: str,
    current_sign_count: int,
) -> AuthenticationResult:
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=rp.origin,
            credential_public_key=base64url_to_bytes(credential_public_key),
            credential_current_sign_count=current_sign_count,
            require_user_verification=True,
        )
    except Exception as exc:
        raise WebAuthnError("authentication verification failed") from exc
    return AuthenticationResult(
        credential_id=credential_id_from_authentication(credential),
        sign_count=verified.new_sign_count,
    )


def verify_sign_counter(*, stored: int, presented: int) -> int:
    """Check the WebAuthn signature counter and return the value to store.

    Args:
        stored: The counter recorded at the last successful assertion.
        presented: The counter in the assertion just received.

    Returns:
        The counter value to persist.

    Raises:
        ClonedAuthenticatorError: If the counter went backwards, or failed to
            advance when the authenticator has demonstrated it keeps one.

    A counter of zero on both sides is accepted. Some authenticators — notably
    platform passkeys that sync across a user's devices — legitimately do not
    implement a counter and always report zero. Rejecting those would rule out
    exactly the authenticators this deployment expects people to use, so the
    rule is: if the authenticator has ever reported a non-zero counter, it must
    keep advancing; if it has never reported one, it is not counting and its
    zeros carry no information either way.
    """
    if stored == 0 and presented == 0:
        return 0

    if presented <= stored:
        raise ClonedAuthenticatorError(stored=stored, presented=presented)

    return presented


def is_enrollment_usable(status: str) -> bool:
    """Whether a device in ``status`` may authenticate.

    Only ``active``. A device sitting in ``pending_approval`` has been
    registered but not yet approved by the owner, and Blueprint §15's
    owner-approved enrollment would mean nothing if it could be used in the
    interim.
    """
    return status == "active"
