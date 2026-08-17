"""Owner console CLI, against a live database.

The CLI is thin — its logic lives in the services — but the wiring is exactly
the part that breaks silently: a mistyped option, a command that never reaches
its service, an exit code that reports success on failure. These tests drive
the real commands end to end.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

from atlas.owner_console.cli import app

pytestmark = [pytest.mark.integration]

runner = CliRunner()


@pytest.fixture
def cli_env(database_url: str, db: Any) -> Any:
    """Point the CLI at the test database for the duration of one test."""
    previous = os.environ.get("ATLAS_DATABASE_URL")
    os.environ["ATLAS_DATABASE_URL"] = database_url.replace(
        "postgresql://", "postgresql+psycopg://"
    )
    yield db
    if previous is None:
        os.environ.pop("ATLAS_DATABASE_URL", None)
    else:
        os.environ["ATLAS_DATABASE_URL"] = previous


def _user(conn: Any, *, owner: bool, name: str) -> UUID:
    user_id = uuid4()
    conn.execute(
        "INSERT INTO identity.users (id, full_name, email, is_owner, status, version) "
        "VALUES (%s, %s, %s, %s, 'active', 1)",
        (user_id, name, f"{user_id}@example.com", owner),
    )
    return user_id


def _device(conn: Any, user_id: UUID, *, status: str = "pending_approval") -> UUID:
    device_id = uuid4()
    conn.execute(
        "INSERT INTO identity.devices "
        "(id, user_id, device_name, passkey_credential_id, public_key, sign_counter, "
        " trust_level, status) "
        "VALUES (%s, %s, 'Owner laptop', %s, 'pk', 0, 'standard', %s)",
        (device_id, user_id, f"cred-{device_id}", status),
    )
    return device_id


class TestAuditVerify:
    def test_reports_a_healthy_chain(self, cli_env: Any) -> None:
        result = runner.invoke(app, ["audit", "verify"])
        assert result.exit_code == 0
        assert "unbroken" in result.stdout

    def test_exits_non_zero_on_a_broken_chain(self, cli_env: Any) -> None:
        """So it can be run from cron or a monitoring check."""
        cli_env.execute(
            "INSERT INTO audit.audit_events (entity_schema, entity_table, action, after_state) "
            "VALUES ('identity','users','create','{\"a\":1}'), "
            "       ('identity','users','update','{\"a\":2}')"
        )
        cli_env.execute("SET session_replication_role = replica")
        cli_env.execute("UPDATE audit.audit_events SET action = 'tampered' WHERE seq = 1")
        cli_env.execute("SET session_replication_role = origin")

        result = runner.invoke(app, ["audit", "verify"])
        assert result.exit_code == 1


class TestDevices:
    def test_pending_queue_lists_only_pending_devices(self, cli_env: Any) -> None:
        """Approved and revoked devices must not appear in the approval queue."""
        user_id = _user(cli_env, owner=True, name="Owner")
        approved = _device(cli_env, user_id, status="active")
        revoked = _device(cli_env, user_id, status="revoked")
        pending = _device(cli_env, user_id)

        result = runner.invoke(app, ["devices", "pending"])
        assert result.exit_code == 0
        assert str(pending) in result.stdout
        assert str(approved) not in result.stdout
        assert str(revoked) not in result.stdout

    def test_pending_lists_an_enrolled_device(self, cli_env: Any) -> None:
        user_id = _user(cli_env, owner=True, name="Owner")
        device_id = _device(cli_env, user_id)

        result = runner.invoke(app, ["devices", "pending"])
        assert result.exit_code == 0
        assert str(device_id) in result.stdout

    def test_owner_can_approve(self, cli_env: Any) -> None:
        owner_id = _user(cli_env, owner=True, name="Owner")
        device_id = _device(cli_env, owner_id)

        result = runner.invoke(
            app, ["devices", "approve", str(device_id), "--owner-id", str(owner_id)]
        )
        assert result.exit_code == 0, result.stdout

        status = cli_env.execute(
            "SELECT status FROM identity.devices WHERE id = %s", (device_id,)
        ).fetchone()[0]
        assert status == "active"

    def test_a_non_owner_cannot_approve(self, cli_env: Any) -> None:
        """Owner-approved enrollment must actually require the owner."""
        not_owner = _user(cli_env, owner=False, name="Someone")
        device_id = _device(cli_env, not_owner)

        result = runner.invoke(
            app, ["devices", "approve", str(device_id), "--owner-id", str(not_owner)]
        )
        assert result.exit_code != 0

        status = cli_env.execute(
            "SELECT status FROM identity.devices WHERE id = %s", (device_id,)
        ).fetchone()[0]
        assert status == "pending_approval"


class TestBreakGlass:
    def test_seal_invoke_revoke(self, cli_env: Any) -> None:
        owner_id = _user(cli_env, owner=True, name="Owner")
        holder_id = _user(cli_env, owner=False, name="Company Secretary")

        sealed = runner.invoke(
            app,
            [
                "break-glass",
                "seal",
                "--owner-id",
                str(owner_id),
                "--holder-id",
                str(holder_id),
                "--reference",
                "safe deposit box 41",
            ],
        )
        assert sealed.exit_code == 0, sealed.stdout

        credential_id = cli_env.execute(
            "SELECT id FROM identity.break_glass_credentials WHERE holder_user_id = %s",
            (holder_id,),
        ).fetchone()[0]

        invoked = runner.invoke(
            app,
            [
                "break-glass",
                "invoke",
                str(credential_id),
                "--holder-id",
                str(holder_id),
                "--reason",
                "owner unreachable; RERA deadline",
            ],
        )
        assert invoked.exit_code == 0, invoked.stdout
        assert "recorded in the audit log" in invoked.stdout

        revoked = runner.invoke(
            app,
            ["break-glass", "revoke", str(credential_id), "--owner-id", str(owner_id)],
        )
        assert revoked.exit_code == 0, revoked.stdout

        status = cli_env.execute(
            "SELECT status FROM identity.break_glass_credentials WHERE id = %s",
            (credential_id,),
        ).fetchone()[0]
        assert status == "revoked"

    def test_invocation_requires_a_reason(self, cli_env: Any) -> None:
        result = runner.invoke(
            app, ["break-glass", "invoke", str(uuid4()), "--holder-id", str(uuid4())]
        )
        assert result.exit_code != 0


class TestConfiguration:
    def test_missing_database_url_is_a_clear_error(self, db: Any) -> None:
        """Credentials come from the environment, never a tracked config file."""
        previous = os.environ.pop("ATLAS_DATABASE_URL", None)
        try:
            result = runner.invoke(app, ["audit", "verify"])
            assert result.exit_code != 0
            # The message goes to stderr; result.output is the combined stream.
            combined = result.output + (result.stderr or "") + str(result.exception)
            assert "ATLAS_DATABASE_URL" in combined
        finally:
            if previous is not None:
                os.environ["ATLAS_DATABASE_URL"] = previous
