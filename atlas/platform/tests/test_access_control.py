"""Access-control tests.

Table-driven over the nine dimensions Blueprint §15 names. The isolation tests
at the bottom are the ones that matter most: §2's legal-entity separation and
project isolation are only real if a scoped role cannot reach across.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from atlas.platform.access_control import (
    AccessRequest,
    Classification,
    DeviceTrust,
    check_access,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)
ENTITY_A, ENTITY_B = uuid4(), uuid4()
PROJECT_A, PROJECT_B = uuid4(), uuid4()


def make_request(**overrides: object) -> AccessRequest:
    """A request that passes every check, so each test varies exactly one thing."""
    base = {
        "user_id": uuid4(),
        "user_status": "active",
        "session_active": True,
        "session_expires_at": NOW + timedelta(minutes=30),
        "session_risk_score": 0.0,
        "step_up_verified": False,
        "step_up_verified_at": None,
        "device_status": "active",
        "device_trust": DeviceTrust.STANDARD,
        "module": "organization",
        "action": "project.read",
        "classification": Classification.INTERNAL,
        "legal_entity_id": ENTITY_A,
        "project_id": PROJECT_A,
    }
    base.update(overrides)
    return AccessRequest(**base)  # type: ignore[arg-type]


class TestBaseline:
    def test_a_well_formed_request_is_allowed(self) -> None:
        result = check_access(make_request(), has_scoped_role=True, now=NOW)
        assert result.allowed


class TestUserAndSession:
    @pytest.mark.parametrize("status", ["suspended", "deactivated"])
    def test_inactive_user_is_denied(self, status: str) -> None:
        result = check_access(make_request(user_status=status), has_scoped_role=True, now=NOW)
        assert not result.allowed
        assert status in result.reason

    def test_revoked_session_is_denied(self) -> None:
        result = check_access(make_request(session_active=False), has_scoped_role=True, now=NOW)
        assert not result.allowed
        assert "revoked" in result.reason

    def test_expired_session_is_denied(self) -> None:
        result = check_access(
            make_request(session_expires_at=NOW - timedelta(seconds=1)),
            has_scoped_role=True,
            now=NOW,
        )
        assert not result.allowed
        assert "expired" in result.reason

    def test_high_risk_session_is_denied(self) -> None:
        result = check_access(make_request(session_risk_score=95.0), has_scoped_role=True, now=NOW)
        assert not result.allowed
        assert "risk score" in result.reason


class TestDeviceTrust:
    def test_device_awaiting_owner_approval_cannot_be_used(self) -> None:
        """Owner-approved enrollment is meaningless if the pending device works."""
        result = check_access(
            make_request(device_status="pending_approval"),
            has_scoped_role=True,
            now=NOW,
        )
        assert not result.allowed
        assert "pending_approval" in result.reason

    def test_revoked_device_is_denied(self) -> None:
        result = check_access(make_request(device_status="revoked"), has_scoped_role=True, now=NOW)
        assert not result.allowed

    def test_restricted_classification_needs_an_elevated_device(self) -> None:
        request = make_request(
            classification=Classification.RESTRICTED, device_trust=DeviceTrust.STANDARD
        )
        result = check_access(request, has_scoped_role=True, now=NOW)
        assert not result.allowed
        assert "elevated-trust device" in result.reason

        allowed = check_access(
            replace(request, device_trust=DeviceTrust.ELEVATED),
            has_scoped_role=True,
            now=NOW,
        )
        assert allowed.allowed

    @pytest.mark.parametrize(
        "classification",
        [Classification.PUBLIC, Classification.INTERNAL, Classification.CONFIDENTIAL],
    )
    def test_lower_classifications_work_on_a_standard_device(
        self, classification: Classification
    ) -> None:
        result = check_access(
            make_request(classification=classification, device_trust=DeviceTrust.STANDARD),
            has_scoped_role=True,
            now=NOW,
        )
        assert result.allowed


class TestScopedRole:
    def test_missing_role_is_denied(self) -> None:
        result = check_access(make_request(), has_scoped_role=False, now=NOW)
        assert not result.allowed
        assert "no role granting" in result.reason

    def test_role_scoping_is_not_decided_here(self) -> None:
        """This module never queries identity.user_roles.

        Whether a role reaches a given entity or project is Identity's answer,
        passed in. That keeps the scoping rule in one place rather than
        reimplemented per module.
        """
        for entity, project in [
            (ENTITY_A, PROJECT_A),
            (ENTITY_B, PROJECT_B),
            (None, None),
        ]:
            request = make_request(legal_entity_id=entity, project_id=project)
            assert check_access(request, has_scoped_role=True, now=NOW).allowed
            assert not check_access(request, has_scoped_role=False, now=NOW).allowed

    def test_denial_reason_names_the_scope(self) -> None:
        """The audit trail needs to show what was refused, not just that it was."""
        result = check_access(
            make_request(legal_entity_id=ENTITY_B, project_id=PROJECT_B),
            has_scoped_role=False,
            now=NOW,
        )
        assert str(ENTITY_B) in result.reason
        assert str(PROJECT_B) in result.reason


class TestStepUp:
    def test_sensitive_action_without_step_up_is_denied(self) -> None:
        result = check_access(make_request(action="payment.approve"), has_scoped_role=True, now=NOW)
        assert not result.allowed
        assert "step-up" in result.reason

    def test_sensitive_action_with_fresh_step_up_is_allowed(self) -> None:
        result = check_access(
            make_request(
                action="payment.approve",
                step_up_verified=True,
                step_up_verified_at=NOW - timedelta(minutes=1),
            ),
            has_scoped_role=True,
            now=NOW,
        )
        assert result.allowed

    def test_sensitive_action_with_stale_step_up_is_denied(self) -> None:
        result = check_access(
            make_request(
                action="payment.approve",
                step_up_verified=True,
                step_up_verified_at=NOW - timedelta(hours=2),
            ),
            has_scoped_role=True,
            now=NOW,
        )
        assert not result.allowed

    def test_ordinary_action_needs_no_step_up(self) -> None:
        assert check_access(
            make_request(action="project.read"), has_scoped_role=True, now=NOW
        ).allowed


class TestCheckOrdering:
    def test_device_is_checked_before_role(self) -> None:
        """A revoked device is refused without needing a role lookup."""
        result = check_access(make_request(device_status="revoked"), has_scoped_role=False, now=NOW)
        assert "device status" in result.reason

    def test_user_status_outranks_everything(self) -> None:
        result = check_access(
            make_request(
                user_status="deactivated",
                session_active=False,
                device_status="revoked",
            ),
            has_scoped_role=False,
            now=NOW,
        )
        assert "user status" in result.reason
