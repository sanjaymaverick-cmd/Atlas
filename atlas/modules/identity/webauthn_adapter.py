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

from dataclasses import dataclass


class WebAuthnError(Exception):
    """Base class for ceremony failures."""


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
class RelyingParty:
    """Who we are, from the authenticator's point of view.

    ``rp_id`` is bound into every credential at registration and cannot be
    changed afterwards without invalidating every enrolled passkey — so it is
    configuration, deliberately not a constant in this file.
    """

    rp_id: str
    rp_name: str
    origin: str


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
