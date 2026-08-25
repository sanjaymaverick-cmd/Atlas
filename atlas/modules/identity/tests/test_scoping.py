"""Role scope tests.

These are the legal-entity separation and project isolation tests. Blueprint §2
lists both as architecture principles; this module is where they are actually
decided, so the cross-entity refusals below are the ones that matter.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from atlas.modules.identity.scoping import RoleGrant, any_grant_covers, grant_covers

pytestmark = pytest.mark.unit

ENTITY_A, ENTITY_B = uuid4(), uuid4()
PROJECT_A1, PROJECT_A2 = uuid4(), uuid4()  # both in ENTITY_A
PROJECT_B1 = uuid4()  # in ENTITY_B

APPROVE = "contract.approve"

GLOBAL = RoleGrant(APPROVE, None, None)
ENTITY_A_GRANT = RoleGrant(APPROVE, ENTITY_A, None)
PROJECT_A1_GRANT = RoleGrant(APPROVE, ENTITY_A, PROJECT_A1)


class TestGlobalGrant:
    def test_reaches_everything(self) -> None:
        assert grant_covers(GLOBAL, legal_entity_id=ENTITY_A, project_id=PROJECT_A1)
        assert grant_covers(GLOBAL, legal_entity_id=ENTITY_B, project_id=PROJECT_B1)
        assert grant_covers(GLOBAL, legal_entity_id=None, project_id=None)


class TestEntityScopedGrant:
    def test_reaches_its_own_entity(self) -> None:
        assert grant_covers(ENTITY_A_GRANT, legal_entity_id=ENTITY_A, project_id=None)

    def test_reaches_projects_within_its_entity(self) -> None:
        assert grant_covers(
            ENTITY_A_GRANT,
            legal_entity_id=ENTITY_A,
            project_id=PROJECT_A2,
            project_entity_id=ENTITY_A,
        )

    def test_does_not_reach_a_sibling_entity(self) -> None:
        """Legal-entity separation, Blueprint §2."""
        assert not grant_covers(ENTITY_A_GRANT, legal_entity_id=ENTITY_B, project_id=None)

    def test_does_not_reach_a_project_in_another_entity(self) -> None:
        assert not grant_covers(
            ENTITY_A_GRANT,
            legal_entity_id=ENTITY_B,
            project_id=PROJECT_B1,
            project_entity_id=ENTITY_B,
        )

    def test_does_not_reach_a_project_whose_entity_is_unknown(self) -> None:
        """Without the project's entity, coverage cannot be shown — so refuse.

        Failing closed matters here: guessing would let an entity-scoped grant
        reach an arbitrary project.
        """
        assert not grant_covers(
            ENTITY_A_GRANT,
            legal_entity_id=None,
            project_id=PROJECT_B1,
            project_entity_id=None,
        )

    def test_does_not_confer_global_authority(self) -> None:
        assert not grant_covers(ENTITY_A_GRANT, legal_entity_id=None, project_id=None)


class TestProjectScopedGrant:
    def test_reaches_its_own_project(self) -> None:
        assert grant_covers(PROJECT_A1_GRANT, legal_entity_id=ENTITY_A, project_id=PROJECT_A1)

    def test_does_not_reach_a_sibling_project(self) -> None:
        """Project isolation, Blueprint §2."""
        assert not grant_covers(PROJECT_A1_GRANT, legal_entity_id=ENTITY_A, project_id=PROJECT_A2)

    def test_does_not_widen_to_the_parent_entity(self) -> None:
        """A project grant is not authority over the entity that owns it."""
        assert not grant_covers(PROJECT_A1_GRANT, legal_entity_id=ENTITY_A, project_id=None)

    def test_does_not_confer_global_authority(self) -> None:
        assert not grant_covers(PROJECT_A1_GRANT, legal_entity_id=None, project_id=None)


class TestPermissionMatching:
    def test_a_grant_for_another_permission_does_not_apply(self) -> None:
        grants = [RoleGrant("project.read", None, None)]
        assert not any_grant_covers(
            grants,
            permission_code=APPROVE,
            legal_entity_id=ENTITY_A,
            project_id=None,
        )

    def test_the_widest_matching_grant_wins(self) -> None:
        grants = [PROJECT_A1_GRANT, GLOBAL]
        assert any_grant_covers(
            grants,
            permission_code=APPROVE,
            legal_entity_id=ENTITY_B,
            project_id=PROJECT_B1,
            project_entity_id=ENTITY_B,
        )

    def test_no_grants_means_no_access(self) -> None:
        assert not any_grant_covers(
            [], permission_code=APPROVE, legal_entity_id=ENTITY_A, project_id=None
        )

    def test_several_narrow_grants_do_not_combine_into_a_wide_one(self) -> None:
        """Holding A and B separately is not authority over the whole estate."""
        grants = [RoleGrant(APPROVE, ENTITY_A, None), RoleGrant(APPROVE, ENTITY_B, None)]
        assert not any_grant_covers(
            grants, permission_code=APPROVE, legal_entity_id=None, project_id=None
        )
