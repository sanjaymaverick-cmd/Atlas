"""Audit hash-chain integrity, end to end against a live database.

Named explicitly in CLAUDE_CODE_KICKOFF.md: "Verify the chain is unbroken as
part of your test suite, not just that rows get written."

These tests read raw rows out of PostgreSQL and hand them to
``atlas.platform.audit.chain.verify_chain``, which recomputes every hash in
Python. Nothing here asks the database whether it believes itself to be
consistent.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from atlas.platform.audit.chain import (
    AuditRecord,
    ChainIntegrityError,
    verify_chain,
)

pytestmark = [pytest.mark.integration]


def _write(conn: Any, entity_schema: str, entity_table: str, action: str, payload: dict) -> None:
    conn.execute(
        """
        INSERT INTO audit.audit_events (entity_schema, entity_table, entity_id, action, after_state)
        VALUES (%s, %s, gen_random_uuid(), %s, %s)
        """,
        (entity_schema, entity_table, action, json.dumps(payload)),
    )


def _read_chain(conn: Any) -> list[AuditRecord]:
    rows = conn.execute(
        """
        SELECT seq, entity_schema, entity_table, entity_id, action,
               after_state::text, occurred_at, prev_hash, record_hash
        FROM audit.audit_events
        ORDER BY seq
        """
    ).fetchall()
    return [
        AuditRecord(
            seq=r[0],
            entity_schema=r[1],
            entity_table=r[2],
            entity_id=r[3],
            action=r[4],
            after_state=r[5],
            occurred_at=r[6],
            prev_hash=r[7],
            record_hash=r[8],
        )
        for r in rows
    ]


class TestChainIntegrity:
    def test_chain_is_unbroken_across_modules(self, db: Any) -> None:
        """Seed events from several modules, then verify the whole chain."""
        _write(db, "organization", "legal_entities", "create", {"name": "Entity A"})
        _write(db, "organization", "projects", "create", {"code": "PRJ-1"})
        _write(db, "identity", "users", "create", {"email": "a@example.com"})
        _write(db, "identity", "devices", "approve", {"trust_level": "standard"})
        _write(db, "organization", "projects", "update", {"code": "PRJ-1", "city": "Pune"})

        chain = _read_chain(db)
        assert len(chain) == 5
        assert verify_chain(chain) == 5

    def test_chain_survives_a_multi_row_transaction(self, db: Any) -> None:
        """The case that originally forked the chain.

        All rows in one statement share a transaction timestamp, so anything
        ordering by created_at cannot tell them apart.
        """
        db.execute(
            """
            INSERT INTO audit.audit_events (entity_schema, entity_table, action, after_state)
            SELECT 'organization', 'projects', 'create', jsonb_build_object('n', g)
            FROM generate_series(1, 50) g
            """
        )
        chain = _read_chain(db)
        assert len(chain) == 50
        assert verify_chain(chain) == 50

    def test_chain_survives_concurrent_writers(self, db: Any, database_url: str) -> None:
        """Concurrent appenders must not fork the chain.

        Sequence allocation happens inside the chain lock precisely so that
        seq order and hash linkage cannot disagree under contention.
        """
        import concurrent.futures

        import psycopg

        def writer(worker: int) -> None:
            with psycopg.connect(database_url, autocommit=True) as conn:
                conn.execute(
                    """
                    INSERT INTO audit.audit_events
                        (entity_schema, entity_table, action, after_state)
                    SELECT 'organization', 'projects', 'create',
                           jsonb_build_object('w', %s, 'r', g)
                    FROM generate_series(1, 20) g
                    """,
                    (worker,),
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(writer, range(8)))

        chain = _read_chain(db)
        assert len(chain) == 160
        assert verify_chain(chain) == 160

    def test_timezone_of_writer_does_not_break_verification(
        self, db: Any, database_url: str
    ) -> None:
        """A record written from Asia/Kolkata must verify from anywhere.

        The hash is taken over a UTC-normalised timestamp; hashing the plain
        ::text cast would make it depend on each client's TimeZone setting.
        """
        import psycopg

        for tz in ("Asia/Kolkata", "UTC", "America/New_York"):
            with psycopg.connect(database_url, autocommit=True) as conn:
                conn.execute(f"SET TimeZone='{tz}'")
                _write(conn, "identity", "users", "create", {"tz": tz})

        chain = _read_chain(db)
        assert len(chain) == 3
        assert verify_chain(chain) == 3


class TestTamperDetection:
    def test_update_is_rejected_by_the_database(self, db: Any) -> None:
        """Append-only is enforced in the database, not by application habit."""
        import psycopg

        _write(db, "identity", "users", "create", {"email": "a@example.com"})
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            db.execute("UPDATE audit.audit_events SET action = 'tampered'")

    def test_delete_is_rejected_by_the_database(self, db: Any) -> None:
        import psycopg

        _write(db, "identity", "users", "create", {"email": "a@example.com"})
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            db.execute("DELETE FROM audit.audit_events")

    def test_verifier_detects_a_row_edited_behind_the_triggers(self, db: Any) -> None:
        """The scenario the hash chain exists for.

        A superuser can disable a trigger and edit the table. The chain is what
        makes that visible afterwards, so this test does exactly that and
        asserts the verifier notices.
        """
        _write(db, "organization", "projects", "create", {"code": "PRJ-1"})
        _write(db, "organization", "projects", "update", {"code": "PRJ-1"})
        _write(db, "organization", "projects", "approve", {"code": "PRJ-1"})

        assert verify_chain(_read_chain(db)) == 3

        db.execute("ALTER TABLE audit.audit_events DISABLE TRIGGER trg_audit_no_update")
        db.execute("UPDATE audit.audit_events SET action = 'reject' WHERE seq = 2")
        db.execute("ALTER TABLE audit.audit_events ENABLE TRIGGER trg_audit_no_update")

        with pytest.raises(ChainIntegrityError, match="has been altered") as exc:
            verify_chain(_read_chain(db))
        assert exc.value.seq == 2

    def test_verifier_detects_a_deleted_row(self, db: Any) -> None:
        _write(db, "organization", "projects", "create", {"code": "PRJ-1"})
        _write(db, "organization", "projects", "update", {"code": "PRJ-2"})
        _write(db, "organization", "projects", "approve", {"code": "PRJ-3"})

        db.execute("ALTER TABLE audit.audit_events DISABLE TRIGGER trg_audit_no_delete")
        db.execute("DELETE FROM audit.audit_events WHERE seq = 2")
        db.execute("ALTER TABLE audit.audit_events ENABLE TRIGGER trg_audit_no_delete")

        with pytest.raises(ChainIntegrityError, match="gap in chain"):
            verify_chain(_read_chain(db))
