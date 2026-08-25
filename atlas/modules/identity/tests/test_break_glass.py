"""Break-glass state machine tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from atlas.modules.identity.break_glass import (
    DEFAULT_GRANT_TTL,
    BreakGlassStatus,
    InvalidTransitionError,
    NotTheHolderError,
    assert_transition,
    can_transition,
    invoke,
    revoke,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)
CREDENTIAL = uuid4()
HOLDER = uuid4()


class TestTransitions:
    @pytest.mark.parametrize(
        ("current", "requested"),
        [
            (BreakGlassStatus.SEALED, BreakGlassStatus.INVOKED),
            (BreakGlassStatus.SEALED, BreakGlassStatus.REVOKED),
            (BreakGlassStatus.INVOKED, BreakGlassStatus.REVOKED),
        ],
    )
    def test_legal_transitions(
        self, current: BreakGlassStatus, requested: BreakGlassStatus
    ) -> None:
        assert can_transition(current, requested)
        assert_transition(current, requested)

    @pytest.mark.parametrize("current", [BreakGlassStatus.INVOKED, BreakGlassStatus.REVOKED])
    def test_cannot_return_to_sealed(self, current: BreakGlassStatus) -> None:
        """The defect the DB CHECK constraint cannot express.

        Re-sealing a used credential would destroy the 'used exactly once, and
        it shows' property the whole mechanism depends on.
        """
        assert not can_transition(current, BreakGlassStatus.SEALED)
        with pytest.raises(InvalidTransitionError, match="cannot be re-sealed"):
            assert_transition(current, BreakGlassStatus.SEALED)

    def test_revoked_is_terminal(self) -> None:
        for target in BreakGlassStatus:
            assert not can_transition(BreakGlassStatus.REVOKED, target)


class TestInvoke:
    def test_holder_can_invoke_a_sealed_credential(self) -> None:
        grant = invoke(
            credential_id=CREDENTIAL,
            holder_user_id=HOLDER,
            invoking_user_id=HOLDER,
            current_status=BreakGlassStatus.SEALED,
            reason="owner unreachable; quarterly filing deadline today",
            now=NOW,
        )
        assert grant.holder_user_id == HOLDER
        assert grant.expires_at == NOW + DEFAULT_GRANT_TTL
        assert grant.is_active(NOW)

    def test_non_holder_cannot_invoke(self) -> None:
        with pytest.raises(NotTheHolderError):
            invoke(
                credential_id=CREDENTIAL,
                holder_user_id=HOLDER,
                invoking_user_id=uuid4(),
                current_status=BreakGlassStatus.SEALED,
                reason="attempting escalation",
                now=NOW,
            )

    def test_cannot_reuse_an_invoked_credential(self) -> None:
        with pytest.raises(InvalidTransitionError):
            invoke(
                credential_id=CREDENTIAL,
                holder_user_id=HOLDER,
                invoking_user_id=HOLDER,
                current_status=BreakGlassStatus.INVOKED,
                reason="second use",
                now=NOW,
            )

    def test_cannot_invoke_a_revoked_credential(self) -> None:
        with pytest.raises(InvalidTransitionError):
            invoke(
                credential_id=CREDENTIAL,
                holder_user_id=HOLDER,
                invoking_user_id=HOLDER,
                current_status=BreakGlassStatus.REVOKED,
                reason="after revocation",
                now=NOW,
            )

    @pytest.mark.parametrize("reason", ["", "   "])
    def test_reason_is_required(self, reason: str) -> None:
        """An emergency escalation with no stated cause is not auditable."""
        with pytest.raises(ValueError, match="reason is required"):
            invoke(
                credential_id=CREDENTIAL,
                holder_user_id=HOLDER,
                invoking_user_id=HOLDER,
                current_status=BreakGlassStatus.SEALED,
                reason=reason,
                now=NOW,
            )


class TestGrantExpiry:
    def test_grant_lapses_on_its_own(self) -> None:
        """An unrevoked invocation must not become a standing second owner."""
        grant = invoke(
            credential_id=CREDENTIAL,
            holder_user_id=HOLDER,
            invoking_user_id=HOLDER,
            current_status=BreakGlassStatus.SEALED,
            reason="owner unreachable",
            now=NOW,
        )
        assert grant.is_active(NOW + DEFAULT_GRANT_TTL - timedelta(seconds=1))
        assert not grant.is_active(NOW + DEFAULT_GRANT_TTL)
        assert not grant.is_active(NOW + timedelta(days=1))

    def test_grant_ttl_matches_the_blueprint_rto(self) -> None:
        assert DEFAULT_GRANT_TTL == timedelta(hours=4)


class TestRevoke:
    @pytest.mark.parametrize("current", [BreakGlassStatus.SEALED, BreakGlassStatus.INVOKED])
    def test_revoke_from_sealed_or_invoked(self, current: BreakGlassStatus) -> None:
        assert revoke(current) is BreakGlassStatus.REVOKED

    def test_cannot_revoke_twice(self) -> None:
        with pytest.raises(InvalidTransitionError):
            revoke(BreakGlassStatus.REVOKED)
