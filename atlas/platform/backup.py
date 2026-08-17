"""Backup observability.

Blueprint §3.2 sets RPO targets of 15 minutes for PostgreSQL via continuous WAL
archiving and 24 hours for object storage via nightly sync. Kickoff item 7 asks
that these jobs are *observable*, not merely scheduled — a backup job that has
silently failed for three weeks looks exactly like one that is working, right
up until a restore is needed.

So this module answers one question: given what the database reports about WAL
archiving and when object storage last synced, is the deployment currently
meeting its stated RPO? The answer is exposed through the owner console and is
meant to be alerted on.

The RPO figures are the blueprint's *recommended defaults* and remain subject
to owner confirmation (§25 item 3). They are parameters here, not constants
buried in a query, so revising them is a configuration change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

DEFAULT_TRANSACTIONAL_RPO = timedelta(minutes=15)
"""Blueprint §3.2, pending owner confirmation."""

DEFAULT_OBJECT_STORAGE_RPO = timedelta(hours=24)
"""Blueprint §3.2, pending owner confirmation."""


class BackupHealth(StrEnum):
    OK = "ok"
    LAGGING = "lagging"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BackupStatus:
    """One backup stream's health."""

    stream: str
    health: BackupHealth
    detail: str
    last_success_at: datetime | None
    rpo_target: timedelta

    @property
    def is_healthy(self) -> bool:
        return self.health is BackupHealth.OK


def assess_wal_archiving(
    *,
    archived_count: int,
    failed_count: int,
    last_archived_at: datetime | None,
    last_failed_at: datetime | None = None,
    now: datetime | None = None,
    rpo: timedelta = DEFAULT_TRANSACTIONAL_RPO,
) -> BackupStatus:
    """Assess WAL archiving from ``pg_stat_archiver``.

    Args:
        archived_count: ``archived_count`` from ``pg_stat_archiver``.
        failed_count: ``failed_count`` from the same view.
        last_archived_at: ``last_archived_time``.
        last_failed_at: ``last_failed_time``.
        now: Current time; injectable for testing.
        rpo: Recovery point objective for the transactional store.

    A non-zero ``failed_count`` alone is not treated as a failure: the counter
    is cumulative since the statistics were last reset, so a transient failure
    six months ago would otherwise pin the status to failed forever. What
    matters is whether the *most recent* attempt failed — that is, whether the
    last failure is more recent than the last success.
    """
    moment = now if now is not None else datetime.now(UTC)

    if archived_count == 0 and last_archived_at is None:
        if failed_count > 0:
            return BackupStatus(
                stream="wal_archiving",
                health=BackupHealth.FAILED,
                detail=(
                    f"WAL archiving has never succeeded and has failed "
                    f"{failed_count} time(s). The transactional RPO is not being met."
                ),
                last_success_at=None,
                rpo_target=rpo,
            )
        return BackupStatus(
            stream="wal_archiving",
            health=BackupHealth.UNKNOWN,
            detail=(
                "WAL archiving has not run. Either archive_mode is off or the "
                "database has not yet completed a segment."
            ),
            last_success_at=None,
            rpo_target=rpo,
        )

    if last_failed_at is not None and (
        last_archived_at is None or last_failed_at > last_archived_at
    ):
        return BackupStatus(
            stream="wal_archiving",
            health=BackupHealth.FAILED,
            detail=(
                f"The most recent WAL archive attempt failed at "
                f"{last_failed_at:%Y-%m-%d %H:%M} UTC, after the last success."
            ),
            last_success_at=last_archived_at,
            rpo_target=rpo,
        )

    # Narrowed by the two branches above: last_archived_at is set whenever we
    # reach here, but the type checker cannot see that across them.
    if last_archived_at is None:  # pragma: no cover - unreachable
        raise AssertionError("last_archived_at should be set at this point")
    lag = moment - last_archived_at
    if lag > rpo:
        return BackupStatus(
            stream="wal_archiving",
            health=BackupHealth.LAGGING,
            detail=(f"Last WAL archive was {_describe(lag)} ago, beyond the {_describe(rpo)} RPO."),
            last_success_at=last_archived_at,
            rpo_target=rpo,
        )

    return BackupStatus(
        stream="wal_archiving",
        health=BackupHealth.OK,
        detail=f"Last WAL archive {_describe(lag)} ago, within the {_describe(rpo)} RPO.",
        last_success_at=last_archived_at,
        rpo_target=rpo,
    )


def assess_object_storage_sync(
    *,
    last_sync_at: datetime | None,
    last_sync_succeeded: bool = True,
    now: datetime | None = None,
    rpo: timedelta = DEFAULT_OBJECT_STORAGE_RPO,
) -> BackupStatus:
    """Assess the nightly object-storage sync."""
    moment = now if now is not None else datetime.now(UTC)

    if last_sync_at is None:
        return BackupStatus(
            stream="object_storage_sync",
            health=BackupHealth.UNKNOWN,
            detail="Object storage has never been synced, or the job does not report.",
            last_success_at=None,
            rpo_target=rpo,
        )

    if not last_sync_succeeded:
        return BackupStatus(
            stream="object_storage_sync",
            health=BackupHealth.FAILED,
            detail=(
                f"The most recent object-storage sync failed at {last_sync_at:%Y-%m-%d %H:%M} UTC."
            ),
            last_success_at=None,
            rpo_target=rpo,
        )

    lag = moment - last_sync_at
    if lag > rpo:
        return BackupStatus(
            stream="object_storage_sync",
            health=BackupHealth.LAGGING,
            detail=(
                f"Last object-storage sync {_describe(lag)} ago, beyond the {_describe(rpo)} RPO."
            ),
            last_success_at=last_sync_at,
            rpo_target=rpo,
        )

    return BackupStatus(
        stream="object_storage_sync",
        health=BackupHealth.OK,
        detail=f"Last object-storage sync {_describe(lag)} ago.",
        last_success_at=last_sync_at,
        rpo_target=rpo,
    )


def overall_health(statuses: list[BackupStatus]) -> BackupHealth:
    """Reduce several streams to one status, worst-first.

    ``UNKNOWN`` ranks alongside failure rather than below it. A stream that
    cannot report is not a stream that is working, and treating silence as
    success is the failure mode this module exists to prevent.
    """
    if not statuses:
        return BackupHealth.UNKNOWN
    for level in (BackupHealth.FAILED, BackupHealth.UNKNOWN, BackupHealth.LAGGING):
        if any(s.health is level for s in statuses):
            return level
    return BackupHealth.OK


def _describe(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


WAL_ARCHIVER_QUERY = """
SELECT archived_count, last_archived_time, failed_count, last_failed_time
FROM pg_stat_archiver
"""
"""What to ask PostgreSQL for ``assess_wal_archiving``'s inputs."""
