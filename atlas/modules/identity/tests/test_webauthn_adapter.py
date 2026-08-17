"""WebAuthn signature-counter tests.

The counter is the specification's clone-detection signal, and
``identity.devices`` had no column for it before Phase 1 — so these tests cover
a check that previously could not exist.
"""

from __future__ import annotations

import pytest

from atlas.modules.identity.webauthn_adapter import (
    ClonedAuthenticatorError,
    is_enrollment_usable,
    verify_sign_counter,
)

pytestmark = pytest.mark.unit


class TestSignCounter:
    def test_advancing_counter_is_accepted(self) -> None:
        assert verify_sign_counter(stored=5, presented=6) == 6

    def test_a_large_jump_is_accepted(self) -> None:
        """The device may have been used offline against another relying party."""
        assert verify_sign_counter(stored=5, presented=500) == 500

    def test_repeated_counter_is_rejected(self) -> None:
        """Two copies of a key cannot both keep counting upwards."""
        with pytest.raises(ClonedAuthenticatorError):
            verify_sign_counter(stored=7, presented=7)

    def test_decreasing_counter_is_rejected(self) -> None:
        with pytest.raises(ClonedAuthenticatorError) as exc:
            verify_sign_counter(stored=9, presented=4)
        assert exc.value.stored == 9
        assert exc.value.presented == 4

    def test_error_says_what_it_suspects(self) -> None:
        """An operator reading the log should see 'cloned', not 'auth failed'."""
        with pytest.raises(ClonedAuthenticatorError, match="cloned"):
            verify_sign_counter(stored=3, presented=3)

    def test_non_counting_authenticator_is_accepted(self) -> None:
        """Synced platform passkeys report zero forever and are legitimate.

        Rejecting these would rule out the authenticators this deployment
        most expects people to use.
        """
        assert verify_sign_counter(stored=0, presented=0) == 0

    def test_a_counting_authenticator_may_not_fall_back_to_zero(self) -> None:
        """Once it has counted, a zero is a regression, not 'not counting'."""
        with pytest.raises(ClonedAuthenticatorError):
            verify_sign_counter(stored=12, presented=0)

    def test_first_advance_from_zero_is_accepted(self) -> None:
        assert verify_sign_counter(stored=0, presented=1) == 1


class TestEnrollmentStatus:
    def test_active_device_may_authenticate(self) -> None:
        assert is_enrollment_usable("active")

    @pytest.mark.parametrize("status", ["pending_approval", "revoked"])
    def test_other_statuses_may_not(self, status: str) -> None:
        """Owner-approved enrollment means nothing if pending devices work."""
        assert not is_enrollment_usable(status)
