"""Audit event writer.

Every mutating action in the system writes one row here, in the same
transaction as the mutation itself (Blueprint §2, "evidence-backed
operations"). The writer lives in the platform layer rather than in the Audit
module so that a module recording an event does not have to depend on Audit —
Organization writes audit rows without importing anything from
``atlas.modules.audit``.

The writer does **not** compute hashes. ``prev_hash``, ``record_hash`` and
``seq`` are assigned by ``audit.compute_record_hash()`` inside the database,
under the chain lock. Computing them in application code would let two
application processes fork the chain, and would put the tamper-evidence
mechanism in exactly the place an attacker with application access could
rewrite it.

There is no update and no delete. The table rejects both, and per §2 the only
way to record that an earlier event was wrong is a further, compensating
event.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT = text(
    """
    INSERT INTO audit.audit_events
        (actor_user_id, entity_schema, entity_table, entity_id,
         action, before_state, after_state)
    VALUES
        (:actor_user_id, :entity_schema, :entity_table, :entity_id,
         :action, CAST(:before_state AS jsonb), CAST(:after_state AS jsonb))
    RETURNING id, seq
    """
)


async def record_event(
    session: AsyncSession,
    *,
    actor_user_id: UUID | None,
    entity_schema: str,
    entity_table: str,
    entity_id: UUID | None,
    action: str,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
) -> tuple[UUID, int]:
    """Append one audit event.

    Args:
        session: The session running the mutation being audited. Passing the
            *same* session is the point: the event and the change it records
            share a transaction and commit together.
        actor_user_id: Who performed the action. ``None`` only for system
            actions with no human actor, such as a scheduled integrity check.
        entity_schema: Schema of the affected table, e.g. ``organization``.
        entity_table: Table name, e.g. ``projects``.
        entity_id: Primary key of the affected row, where there is one.
        action: What happened — ``create``, ``update``, ``approve``,
            ``delete_attempt``, and so on.
        before_state: Prior column values, for updates.
        after_state: Resulting column values.

    Returns:
        The new event's id and its chain position.

    Note that ``before_state`` is stored but deliberately **not** hashed; the
    database's hash covers ``after_state`` only. An attacker able to rewrite
    history would have to alter ``after_state`` to change what the record says
    happened, and that is what the chain detects.
    """
    result = await session.execute(
        _INSERT,
        {
            "actor_user_id": actor_user_id,
            "entity_schema": entity_schema,
            "entity_table": entity_table,
            "entity_id": entity_id,
            "action": action,
            "before_state": json.dumps(before_state, default=str)
            if before_state is not None
            else None,
            "after_state": json.dumps(after_state, default=str)
            if after_state is not None
            else None,
        },
    )
    row = result.one()
    return row.id, row.seq
