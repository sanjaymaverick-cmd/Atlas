"""Chain verifier tests.

The vector tests below are the load-bearing ones. ``verify_chain`` exists to
catch a database whose audit log has been altered; if it computed hashes by
asking that same database, it would prove only self-consistency. So the
expected hashes here were produced by a live PostgreSQL 16 running
``audit.compute_record_hash()`` and are pinned as literals. If either
implementation drifts, these fail.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from atlas.platform.audit.chain import (
    GENESIS_PREV_HASH,
    AuditRecord,
    ChainIntegrityError,
    compute_record_hash,
    format_timestamptz,
    verify_chain,
)

pytestmark = pytest.mark.unit

# Produced by PostgreSQL 16.15 running db/schema.sql. Rows 1-2 were written by a
# session on Asia/Kolkata and row 3 by one on UTC, then read back from a third
# timezone — so these vectors also pin the timezone-independence of the hash.
_H1 = "3729ee6cc8e29b0eb5d0079857922b8d59d77beb6a9ee84a129375cd37a83e0c"
_H2 = "070a29ed36b8d6c447f299ba14b6a6a785a12c59e86125326885841120ab02ee"
_H3 = "bed8807cf81a180bbb79892e5f7954e13cb1e2ff3c7881c051d71219d0790afd"

VECTORS = [
    AuditRecord(
        seq=1,
        entity_schema="organization",
        entity_table="projects",
        entity_id=UUID("11111111-1111-1111-1111-111111111111"),
        action="create",
        after_state='{"a": 1}',
        occurred_at=datetime(2026, 8, 17, 10, 30, 0, tzinfo=UTC),
        prev_hash=GENESIS_PREV_HASH,
        record_hash=_H1,
    ),
    # null entity_id and null after_state — the COALESCE-to-empty-string paths
    AuditRecord(
        seq=2,
        entity_schema="identity",
        entity_table="users",
        entity_id=None,
        action="delete_attempt",
        after_state=None,
        occurred_at=datetime(2026, 8, 17, 10, 30, 0, 123456, tzinfo=UTC),
        prev_hash=_H1,
        record_hash=_H2,
    ),
    # fractional seconds that PostgreSQL would render as ".5" under ::text but
    # ".500000" under the to_char pattern the trigger actually uses
    AuditRecord(
        seq=3,
        entity_schema="identity",
        entity_table="devices",
        entity_id=UUID("22222222-2222-2222-2222-222222222222"),
        action="approve",
        after_state='{"b": "x"}',
        occurred_at=datetime(2026, 8, 17, 10, 30, 0, 500000, tzinfo=UTC),
        prev_hash=_H2,
        record_hash=_H3,
    ),
]


class TestFormatTimestamptz:
    def test_matches_postgres_to_char_pattern(self) -> None:
        value = datetime(2026, 8, 17, 10, 30, 0, tzinfo=UTC)
        assert format_timestamptz(value) == "2026-08-17 10:30:00.000000"

    def test_always_six_fractional_digits(self) -> None:
        value = datetime(2026, 8, 17, 10, 30, 0, 500000, tzinfo=UTC)
        # not ".5" — the trigger's to_char pattern pads to six
        assert format_timestamptz(value) == "2026-08-17 10:30:00.500000"

    def test_normalises_to_utc(self) -> None:
        """The same instant in any timezone must format identically.

        This is the property that makes a record written from Asia/Kolkata
        verifiable from anywhere else.
        """
        instant_utc = datetime(2026, 8, 17, 10, 30, 0, tzinfo=UTC)
        instant_ist = datetime(
            2026, 8, 17, 16, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
        )
        assert instant_utc == instant_ist  # same moment
        assert format_timestamptz(instant_utc) == format_timestamptz(instant_ist)

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            format_timestamptz(datetime(2026, 8, 17, 10, 30, 0))


class TestComputeRecordHash:
    @pytest.mark.parametrize("record", VECTORS, ids=lambda r: f"seq{r.seq}")
    def test_matches_postgres(self, record: AuditRecord) -> None:
        """Independently recompute what the database trigger computed."""
        assert (
            compute_record_hash(
                prev_hash=record.prev_hash,
                entity_schema=record.entity_schema,
                entity_table=record.entity_table,
                entity_id=record.entity_id,
                action=record.action,
                after_state=record.after_state,
                occurred_at=record.occurred_at,
            )
            == record.record_hash
        )

    def test_timezone_of_input_does_not_change_the_hash(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))

        def hash_at(moment: datetime) -> str:
            return compute_record_hash(
                prev_hash=GENESIS_PREV_HASH,
                entity_schema="identity",
                entity_table="users",
                entity_id=None,
                action="create",
                after_state=None,
                occurred_at=moment,
            )

        assert hash_at(datetime(2026, 8, 17, 10, 30, tzinfo=UTC)) == hash_at(
            datetime(2026, 8, 17, 16, 0, tzinfo=ist)
        )


class TestVerifyChain:
    def test_accepts_a_good_chain(self) -> None:
        assert verify_chain(list(VECTORS)) == 3

    def test_empty_chain_is_valid(self) -> None:
        assert verify_chain([]) == 0

    def test_detects_altered_content(self) -> None:
        """The point of the whole mechanism: edited content no longer hashes."""
        tampered = list(VECTORS)
        tampered[1] = replace(VECTORS[1], action="approve")  # was 'delete_attempt'
        with pytest.raises(ChainIntegrityError, match="has been altered") as exc:
            verify_chain(tampered)
        assert exc.value.seq == 2

    def test_detects_broken_link(self) -> None:
        relinked = list(VECTORS)
        relinked[2] = replace(VECTORS[2], prev_hash=_H1)
        with pytest.raises(ChainIntegrityError, match="broken link") as exc:
            verify_chain(relinked)
        assert exc.value.seq == 3

    def test_detects_removed_record(self) -> None:
        """Deleting a middle row leaves a seq gap even if hashes are untouched."""
        with pytest.raises(ChainIntegrityError, match="gap in chain") as exc:
            verify_chain([VECTORS[0], VECTORS[2]])
        assert exc.value.seq == 3

    def test_detects_truncated_head(self) -> None:
        """Removing the oldest records leaves the chain unanchored."""
        with pytest.raises(ChainIntegrityError, match="genesis"):
            verify_chain(list(VECTORS[1:]))

    def test_rejects_unordered_input(self) -> None:
        with pytest.raises(ChainIntegrityError, match="ascending seq order"):
            verify_chain(list(reversed(VECTORS)))
