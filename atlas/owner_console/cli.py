"""Owner console — command line interface.

Phase 1 delivers the owner console as an admin API plus this CLI rather than a
web UI. No frontend framework has been chosen, and building browser screens
ahead of a tested passkey ceremony would be premature. The CLI means the owner
has a working tool for device approval and break-glass management from day one,
and it calls the same services the API will.

Every command that mutates writes an audit event through the service layer;
none of them touch tables directly.
"""

from __future__ import annotations

import asyncio
import os
from uuid import UUID

import typer
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.service import IdentityService
from atlas.platform.audit.chain import ChainIntegrityError, verify_chain
from atlas.platform.db import create_engine, create_session_factory, transaction

app = typer.Typer(
    help="Atlas owner console.",
    no_args_is_help=True,
    add_completion=False,
)
devices_app = typer.Typer(help="Registered device administration.", no_args_is_help=True)
break_glass_app = typer.Typer(
    help="Break-glass credential administration (Blueprint §3.2).", no_args_is_help=True
)
audit_app = typer.Typer(help="Audit log verification.", no_args_is_help=True)
app.add_typer(devices_app, name="devices")
app.add_typer(break_glass_app, name="break-glass")
app.add_typer(audit_app, name="audit")


def _database_url() -> str:
    url = os.environ.get("ATLAS_DATABASE_URL")
    if not url:
        raise typer.BadParameter(
            "ATLAS_DATABASE_URL is not set. The console reads it from the "
            "environment rather than a config file so credentials are not "
            "written to disk (Blueprint §3.3)."
        )
    return url


def _run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


async def _with_session(fn: object) -> object:
    engine = create_engine(_database_url())
    factory = create_session_factory(engine)
    try:
        async with transaction(factory) as session:
            return await fn(session)  # type: ignore[operator]
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# devices
# ---------------------------------------------------------------------------


@devices_app.command("pending")
def devices_pending() -> None:
    """List devices awaiting owner approval."""

    async def run(session: AsyncSession) -> None:
        devices = await IdentityService().list_pending_devices(session)
        if not devices:
            typer.echo("No devices are awaiting approval.")
            return
        typer.echo(f"{len(devices)} device(s) awaiting approval:\n")
        for d in devices:
            typer.echo(f"  {d.id}  user={d.user_id}  {d.device_name or '(unnamed)'}")
            typer.echo(f"      enrolled {d.enrolled_at:%Y-%m-%d %H:%M} UTC")

    _run(_with_session(run))


@devices_app.command("approve")
def devices_approve(
    device_id: str = typer.Argument(..., help="Device UUID to approve."),
    owner_id: str = typer.Option(..., "--owner-id", help="Approving owner's user UUID."),
) -> None:
    """Approve a device so it can authenticate.

    Until approved, an enrolled device authenticates nobody — Blueprint §15's
    owner-approved enrollment.
    """

    async def run(session: AsyncSession) -> None:
        device = await IdentityService().approve_device(
            session, approver_user_id=UUID(owner_id), device_id=UUID(device_id)
        )
        typer.echo(f"Approved device {device.id} ({device.device_name or 'unnamed'}).")

    _run(_with_session(run))


@devices_app.command("revoke")
def devices_revoke(
    device_id: str = typer.Argument(..., help="Device UUID to revoke."),
    actor_id: str = typer.Option(..., "--actor-id", help="Acting user's UUID."),
) -> None:
    """Revoke a device. Takes effect immediately for new requests."""

    async def run(session: AsyncSession) -> None:
        await IdentityService().revoke_device(
            session, actor_user_id=UUID(actor_id), device_id=UUID(device_id)
        )
        typer.echo(f"Revoked device {device_id}.")

    _run(_with_session(run))


# ---------------------------------------------------------------------------
# break-glass
# ---------------------------------------------------------------------------


@break_glass_app.command("seal")
def break_glass_seal(
    holder_id: str = typer.Option(..., "--holder-id", help="Holder's user UUID."),
    reference: str = typer.Option(
        ...,
        "--reference",
        help="Pointer to the physically-secured credential, e.g. 'safe deposit box 41'.",
    ),
    owner_id: str = typer.Option(..., "--owner-id", help="Owner's user UUID."),
) -> None:
    """Register a sealed break-glass credential.

    The reference is a pointer to physically-secured material, never the
    credential itself — storing the secret here would defeat the purpose of
    sealing it outside the system it exists to recover.
    """

    async def run(session: AsyncSession) -> None:
        credential_id = await IdentityService().seal_break_glass(
            session,
            owner_user_id=UUID(owner_id),
            holder_user_id=UUID(holder_id),
            sealed_reference=reference,
        )
        typer.echo(f"Sealed break-glass credential {credential_id}.")
        typer.echo(f"Holder: {holder_id}")
        typer.echo(f"Reference: {reference}")

    _run(_with_session(run))


@break_glass_app.command("invoke")
def break_glass_invoke(
    credential_id: str = typer.Argument(..., help="Credential UUID."),
    holder_id: str = typer.Option(..., "--holder-id", help="Invoking holder's UUID."),
    reason: str = typer.Option(..., "--reason", help="Why the credential is being invoked."),
) -> None:
    """Invoke a sealed credential when the owner is unreachable.

    Authorised on holder identity, not owner approval — the owner being
    unreachable is the triggering condition. Single use: re-arming means
    sealing a new credential.
    """

    async def run(session: AsyncSession) -> None:
        grant = await IdentityService().invoke_break_glass(
            session,
            credential_id=UUID(credential_id),
            invoking_user_id=UUID(holder_id),
            reason=reason,
        )
        typer.echo(f"Break-glass invoked. Authority expires {grant.expires_at:%Y-%m-%d %H:%M} UTC.")
        typer.echo("This invocation has been recorded in the audit log.")

    _run(_with_session(run))


@break_glass_app.command("revoke")
def break_glass_revoke(
    credential_id: str = typer.Argument(..., help="Credential UUID."),
    owner_id: str = typer.Option(..., "--owner-id", help="Owner's user UUID."),
) -> None:
    """Revoke a credential and terminate the holder's sessions immediately."""

    async def run(session: AsyncSession) -> None:
        await IdentityService().revoke_break_glass(
            session, actor_user_id=UUID(owner_id), credential_id=UUID(credential_id)
        )
        typer.echo(f"Revoked credential {credential_id} and terminated holder sessions.")

    _run(_with_session(run))


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


@audit_app.command("verify")
def audit_verify() -> None:
    """Walk the audit chain and recompute every hash.

    Exits non-zero if the chain does not verify, so it can be run from cron or
    a monitoring check.
    """
    from sqlalchemy import text

    from atlas.platform.audit.chain import AuditRecord

    async def run(session: AsyncSession) -> None:
        rows = (
            await session.execute(
                text(
                    "SELECT seq, entity_schema, entity_table, entity_id, action, "
                    "after_state::text, occurred_at, prev_hash, record_hash "
                    "FROM audit.audit_events ORDER BY seq"
                )
            )
        ).all()
        chain = [AuditRecord(*row) for row in rows]
        try:
            count = verify_chain(chain)
        except ChainIntegrityError as exc:
            typer.secho(f"AUDIT CHAIN FAILED VERIFICATION: {exc}", fg=typer.colors.RED, err=True)
            if exc.seq is not None:
                typer.secho(f"First discrepancy at seq={exc.seq}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc
        typer.secho(f"Audit chain verified: {count} record(s), unbroken.", fg=typer.colors.GREEN)

    _run(_with_session(run))


if __name__ == "__main__":  # pragma: no cover
    app()
