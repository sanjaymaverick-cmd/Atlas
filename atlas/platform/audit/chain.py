"""Audit hash-chain computation and verification.

Blueprint §5.2: each audit record carries a hash of the previous record plus its
own content, so a retroactive edit — including one made by a superuser bypassing
the append-only triggers — breaks the chain and is detectable.

The hash formula here is a deliberate second implementation of the one in
``audit.compute_record_hash()`` (``db/schema.sql``). Verifying the database with
a function computed *by* the database would only prove it is self-consistent,
which is exactly what an attacker who has rewritten the trigger would want. The
two must be kept in step; ``test_chain_hash_computation.py`` pins the formula
against fixed vectors so a drift in either is caught.

Ordering is by ``seq`` and only by ``seq``. ``created_at`` is transaction-scoped
and ``id`` is a random UUID, so neither orders the chain — see
``docs/schema-findings-phase1.md``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

GENESIS_PREV_HASH = "0" * 64
"""Anchor for the first record. A chain whose first row does not carry this has
been truncated at the head."""


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One audit row, as far as chain verification is concerned."""

    seq: int
    entity_schema: str
    entity_table: str
    entity_id: UUID | None
    action: str
    after_state: str | None
    occurred_at: datetime
    prev_hash: str
    record_hash: str


class ChainIntegrityError(Exception):
    """Raised when the audit chain does not verify.

    Carries the failing sequence position so an operator can go straight to the
    affected record rather than re-deriving where the break is.
    """

    def __init__(self, message: str, *, seq: int | None = None) -> None:
        super().__init__(message)
        self.seq = seq


def compute_record_hash(
    *,
    prev_hash: str,
    entity_schema: str,
    entity_table: str,
    entity_id: UUID | None,
    action: str,
    after_state: str | None,
    occurred_at: datetime,
) -> str:
    """Recompute a record's hash.

    Mirrors ``audit.compute_record_hash()`` exactly: sha256 over the
    concatenation of the previous hash, the entity coordinates, the action, the
    serialised after-state and the occurrence timestamp, with NULLs rendered as
    the empty string.

    ``occurred_at`` must be rendered the way PostgreSQL renders ``timestamptz``
    in a text cast, since that is what the trigger hashed. See
    ``format_timestamptz``.
    """
    payload = (
        prev_hash
        + entity_schema
        + entity_table
        + (str(entity_id) if entity_id is not None else "")
        + action
        + (after_state if after_state is not None else "")
        + format_timestamptz(occurred_at)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def format_timestamptz(value: datetime) -> str:
    """Render a timestamp the way the trigger hashes it.

    Mirrors ``to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.US')``:
    normalised to UTC, space separator, always exactly six fractional digits,
    and no offset suffix.

    The offset is deliberately absent. Including it would make the hash depend
    on the writing session's ``TimeZone`` setting, so a record written from
    Asia/Kolkata could not be verified from UTC — see
    ``docs/schema-findings-phase1.md``.
    """
    if value.utcoffset() is None:
        raise ValueError("occurred_at must be timezone-aware to hash deterministically")

    utc = value.astimezone(UTC)
    return f"{utc.strftime('%Y-%m-%d %H:%M:%S')}.{utc.microsecond:06d}"


def verify_chain(records: list[AuditRecord]) -> int:
    """Verify an audit chain end to end.

    Checks, in order: that ``seq`` is contiguous and ascending, that the first
    record is anchored to the genesis hash, that each record's stored hash
    matches a recomputation of its own content, and that each record's
    ``prev_hash`` equals its predecessor's ``record_hash``.

    Args:
        records: The chain, ordered by ``seq`` ascending. An empty list is a
            valid (empty) chain.

    Returns:
        The number of records verified.

    Raises:
        ChainIntegrityError: On the first discrepancy found.
    """
    if not records:
        return 0

    ordered = sorted(records, key=lambda r: r.seq)
    if ordered != records:
        raise ChainIntegrityError("records were not supplied in ascending seq order")

    first = ordered[0]
    if first.prev_hash != GENESIS_PREV_HASH:
        raise ChainIntegrityError(
            "chain head is not anchored to the genesis hash — records are missing "
            f"before seq={first.seq}",
            seq=first.seq,
        )

    previous: AuditRecord | None = None
    for record in ordered:
        if previous is not None:
            if record.seq != previous.seq + 1:
                raise ChainIntegrityError(
                    f"gap in chain: seq jumps from {previous.seq} to {record.seq}",
                    seq=record.seq,
                )
            if record.prev_hash != previous.record_hash:
                raise ChainIntegrityError(
                    f"broken link at seq={record.seq}: prev_hash does not match the "
                    f"record_hash of seq={previous.seq}",
                    seq=record.seq,
                )

        expected = compute_record_hash(
            prev_hash=record.prev_hash,
            entity_schema=record.entity_schema,
            entity_table=record.entity_table,
            entity_id=record.entity_id,
            action=record.action,
            after_state=record.after_state,
            occurred_at=record.occurred_at,
        )
        if expected != record.record_hash:
            raise ChainIntegrityError(
                f"record at seq={record.seq} has been altered: its content does not "
                "hash to its stored record_hash",
                seq=record.seq,
            )

        previous = record

    return len(ordered)
