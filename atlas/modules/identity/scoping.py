"""Role scope resolution.

``identity.user_roles`` binds a role to a user with an optional
``legal_entity_id`` and an optional ``project_id``. This module decides what
those bindings mean, and it is the only place that decides it — Blueprint §2's
legal-entity separation and project isolation are exactly this rule, so a
second implementation elsewhere would be a second, divergent security policy.

The rule, stated once:

* Both null — a global grant. Reaches everything.
* Legal entity set, project null — reaches that entity and every project
  within it.
* Project set — reaches only that project.

Scoping narrows and never widens. A grant cannot reach a sibling entity, and a
request that names no scope is only satisfied by a global grant, because a
scoped grant is not evidence of authority over the whole estate.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RoleGrant:
    """One row of ``identity.user_roles``, reduced to what scoping needs."""

    permission_code: str
    legal_entity_id: UUID | None
    project_id: UUID | None

    @property
    def is_global(self) -> bool:
        return self.legal_entity_id is None and self.project_id is None


def grant_covers(
    grant: RoleGrant,
    *,
    legal_entity_id: UUID | None,
    project_id: UUID | None,
    project_entity_id: UUID | None = None,
) -> bool:
    """Whether ``grant`` authorises action in the requested scope.

    Args:
        grant: The grant held by the user.
        legal_entity_id: Legal entity the request concerns, if any.
        project_id: Project the request concerns, if any.
        project_entity_id: The legal entity that ``project_id`` belongs to.
            Supplied by the caller because Identity does not read
            ``organization.projects`` — that would be a boundary violation in
            the opposite direction. Without it, an entity-scoped grant cannot
            be shown to cover a project and is refused.

    Returns:
        Whether the grant reaches the requested scope.
    """
    if grant.is_global:
        return True

    # Project-scoped grant: reaches that project and nothing else. In
    # particular it does not confer authority over the parent entity, which
    # would be a widening.
    if grant.project_id is not None:
        return project_id is not None and grant.project_id == project_id

    # Entity-scoped grant.
    if grant.legal_entity_id is not None:
        if legal_entity_id is not None and grant.legal_entity_id == legal_entity_id:
            # If a project is also named it must belong to that same entity;
            # otherwise the request is asking to reach across entities.
            if project_id is None:
                return True
            return project_entity_id == grant.legal_entity_id
        if project_id is not None and legal_entity_id is None:
            return project_entity_id == grant.legal_entity_id
        return False

    return False  # pragma: no cover - unreachable given is_global above


def any_grant_covers(
    grants: list[RoleGrant],
    *,
    permission_code: str,
    legal_entity_id: UUID | None,
    project_id: UUID | None,
    project_entity_id: UUID | None = None,
) -> bool:
    """Whether any of the user's grants authorises ``permission_code`` here."""
    return any(
        grant_covers(
            grant,
            legal_entity_id=legal_entity_id,
            project_id=project_id,
            project_entity_id=project_entity_id,
        )
        for grant in grants
        if grant.permission_code == permission_code
    )
