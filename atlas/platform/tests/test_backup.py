"""Backup observability tests.

The point of these is that a silently-failed backup must not read as healthy.
Several tests below exist specifically to pin that down.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from atlas.platform.backup import (
    DEFAULT_OBJECT_STORAGE_RPO,
    DEFAULT_TRANSACTIONAL_RPO,
    BackupHealth,
    assess_object_storage_sync,
    assess_wal_archiving,
    overall_health,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)


class TestWalArchiving:
    def test_recent_archive_is_healthy(self) -> None:
        status = assess_wal_archiving(
            archived_count=1200,
            failed_count=0,
            last_archived_at=NOW - timedelta(minutes=2),
            now=NOW,
        )
        assert status.health is BackupHealth.OK

    def test_stale_archive_is_lagging(self) -> None:
        """Beyond the 15-minute RPO the deployment is out of compliance."""
        status = assess_wal_archiving(
            archived_count=1200,
            failed_count=0,
            last_archived_at=NOW - timedelta(hours=3),
            now=NOW,
        )
        assert status.health is BackupHealth.LAGGING
        assert "3h" in status.detail

    def test_never_run_is_unknown_not_ok(self) -> None:
        """Silence must never read as success."""
        status = assess_wal_archiving(
            archived_count=0, failed_count=0, last_archived_at=None, now=NOW
        )
        assert status.health is BackupHealth.UNKNOWN

    def test_never_succeeded_but_failed_is_failed(self) -> None:
        status = assess_wal_archiving(
            archived_count=0,
            failed_count=17,
            last_archived_at=None,
            last_failed_at=NOW - timedelta(minutes=1),
            now=NOW,
        )
        assert status.health is BackupHealth.FAILED

    def test_most_recent_attempt_failed_is_failed(self) -> None:
        status = assess_wal_archiving(
            archived_count=1200,
            failed_count=3,
            last_archived_at=NOW - timedelta(minutes=30),
            last_failed_at=NOW - timedelta(minutes=1),
            now=NOW,
        )
        assert status.health is BackupHealth.FAILED
        assert "after the last success" in status.detail

    def test_an_old_failure_does_not_pin_the_status(self) -> None:
        """failed_count is cumulative since the stats were last reset.

        A transient failure six months ago must not mark the stream failed
        forever — otherwise the signal becomes noise and gets ignored.
        """
        status = assess_wal_archiving(
            archived_count=50_000,
            failed_count=2,
            last_archived_at=NOW - timedelta(minutes=1),
            last_failed_at=NOW - timedelta(days=180),
            now=NOW,
        )
        assert status.health is BackupHealth.OK

    def test_rpo_boundary_is_inclusive(self) -> None:
        status = assess_wal_archiving(
            archived_count=10,
            failed_count=0,
            last_archived_at=NOW - DEFAULT_TRANSACTIONAL_RPO,
            now=NOW,
        )
        assert status.health is BackupHealth.OK


class TestObjectStorageSync:
    def test_recent_sync_is_healthy(self) -> None:
        status = assess_object_storage_sync(last_sync_at=NOW - timedelta(hours=2), now=NOW)
        assert status.health is BackupHealth.OK

    def test_missed_nightly_sync_is_lagging(self) -> None:
        status = assess_object_storage_sync(last_sync_at=NOW - timedelta(days=3), now=NOW)
        assert status.health is BackupHealth.LAGGING

    def test_never_synced_is_unknown(self) -> None:
        assert assess_object_storage_sync(last_sync_at=None, now=NOW).health is BackupHealth.UNKNOWN

    def test_failed_sync_is_failed(self) -> None:
        status = assess_object_storage_sync(
            last_sync_at=NOW - timedelta(minutes=5), last_sync_succeeded=False, now=NOW
        )
        assert status.health is BackupHealth.FAILED
        assert status.last_success_at is None

    def test_uses_the_24_hour_rpo(self) -> None:
        assert DEFAULT_OBJECT_STORAGE_RPO == timedelta(hours=24)


class TestOverallHealth:
    def test_all_healthy(self) -> None:
        statuses = [
            assess_wal_archiving(archived_count=1, failed_count=0, last_archived_at=NOW, now=NOW),
            assess_object_storage_sync(last_sync_at=NOW, now=NOW),
        ]
        assert overall_health(statuses) is BackupHealth.OK

    def test_one_failure_dominates(self) -> None:
        statuses = [
            assess_wal_archiving(
                archived_count=1,
                failed_count=1,
                last_archived_at=NOW - timedelta(hours=1),
                last_failed_at=NOW,
                now=NOW,
            ),
            assess_object_storage_sync(last_sync_at=NOW, now=NOW),
        ]
        assert overall_health(statuses) is BackupHealth.FAILED

    def test_unknown_outranks_lagging(self) -> None:
        """A stream that cannot report is not a stream that is working."""
        statuses = [
            assess_wal_archiving(archived_count=0, failed_count=0, last_archived_at=None, now=NOW),
            assess_object_storage_sync(last_sync_at=NOW - timedelta(days=3), now=NOW),
        ]
        assert overall_health(statuses) is BackupHealth.UNKNOWN

    def test_no_streams_at_all_is_unknown(self) -> None:
        assert overall_health([]) is BackupHealth.UNKNOWN
