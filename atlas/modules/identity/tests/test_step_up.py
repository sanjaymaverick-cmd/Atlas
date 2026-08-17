"""Step-up policy tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from atlas.modules.identity.step_up import (
    DEFAULT_STEP_UP_TTL,
    SensitiveAction,
    StepUpRequiredError,
    assert_step_up,
    is_step_up_fresh,
    requires_step_up,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)


class TestSensitiveActionList:
    @pytest.mark.parametrize(
        "action",
        [
            "contract.approve",
            "payment.approve",
            "party.bank_details.change",
            "vendor.master.change",
            "customer.price.override",
            "document.download",
            "user.role.modify",
            "device.enroll",
            "audit.export",
            "backup.restore",
        ],
    )
    def test_blueprint_section_15_actions_all_require_step_up(self, action: str) -> None:
        assert requires_step_up(action)

    def test_break_glass_invocation_requires_step_up(self) -> None:
        """Not named in §15, but it grants owner-level authority (§3.2)."""
        assert requires_step_up(SensitiveAction.BREAK_GLASS_INVOKE)

    def test_ordinary_action_does_not_require_step_up(self) -> None:
        assert not requires_step_up("project.read")


class TestFreshness:
    def test_fresh_step_up_is_valid(self) -> None:
        assert is_step_up_fresh(
            step_up_verified=True,
            step_up_verified_at=NOW - timedelta(minutes=1),
            now=NOW,
        )

    def test_expired_step_up_is_not_valid(self) -> None:
        """The defect this module exists to close: a boolean that never decays."""
        assert not is_step_up_fresh(
            step_up_verified=True,
            step_up_verified_at=NOW - DEFAULT_STEP_UP_TTL - timedelta(seconds=1),
            now=NOW,
        )

    def test_boundary_is_inclusive(self) -> None:
        assert is_step_up_fresh(
            step_up_verified=True,
            step_up_verified_at=NOW - DEFAULT_STEP_UP_TTL,
            now=NOW,
        )

    def test_flag_set_without_timestamp_is_stale(self) -> None:
        """A row predating the freshness column cannot be shown to be recent."""
        assert not is_step_up_fresh(step_up_verified=True, step_up_verified_at=None, now=NOW)

    def test_timestamp_without_flag_is_not_valid(self) -> None:
        assert not is_step_up_fresh(step_up_verified=False, step_up_verified_at=NOW, now=NOW)

    def test_future_timestamp_is_rejected(self) -> None:
        """A clock problem or a forged row is not evidence of a recent ceremony."""
        assert not is_step_up_fresh(
            step_up_verified=True,
            step_up_verified_at=NOW + timedelta(minutes=10),
            now=NOW,
        )

    def test_naive_timestamp_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            is_step_up_fresh(
                step_up_verified=True,
                step_up_verified_at=datetime(2026, 8, 17, 12, 0, 0),
                now=NOW,
            )


class TestAssertStepUp:
    def test_permits_sensitive_action_with_fresh_step_up(self) -> None:
        assert_step_up(
            action=SensitiveAction.PAYMENT_APPROVAL,
            step_up_verified=True,
            step_up_verified_at=NOW - timedelta(minutes=1),
            now=NOW,
        )

    def test_permits_ordinary_action_without_step_up(self) -> None:
        assert_step_up(
            action="project.read",
            step_up_verified=False,
            step_up_verified_at=None,
            now=NOW,
        )

    def test_blocks_sensitive_action_without_step_up(self) -> None:
        with pytest.raises(StepUpRequiredError, match="has not completed step-up"):
            assert_step_up(
                action=SensitiveAction.CONTRACT_APPROVAL,
                step_up_verified=False,
                step_up_verified_at=None,
                now=NOW,
            )

    def test_blocks_sensitive_action_with_expired_step_up(self) -> None:
        with pytest.raises(StepUpRequiredError, match="expired") as exc:
            assert_step_up(
                action=SensitiveAction.AUDIT_EXPORT,
                step_up_verified=True,
                step_up_verified_at=NOW - timedelta(hours=1),
                now=NOW,
            )
        assert exc.value.action is SensitiveAction.AUDIT_EXPORT

    def test_one_step_up_does_not_authorise_a_later_action(self) -> None:
        """The concrete scenario: approve a contract, then release a payment an
        hour later on the same session."""
        step_up_at = NOW
        assert_step_up(
            action=SensitiveAction.CONTRACT_APPROVAL,
            step_up_verified=True,
            step_up_verified_at=step_up_at,
            now=NOW,
        )
        with pytest.raises(StepUpRequiredError):
            assert_step_up(
                action=SensitiveAction.PAYMENT_APPROVAL,
                step_up_verified=True,
                step_up_verified_at=step_up_at,
                now=NOW + timedelta(hours=1),
            )
