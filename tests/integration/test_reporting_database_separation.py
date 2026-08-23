"""Phase 10 dashboard reads against a physically distinct reporting database."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.reporting.contracts import ReportingUnavailableError
from atlas.modules.reporting.service import ReportingService

pytestmark = [pytest.mark.integration]

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


class AllowAllIdentity:
    def __init__(self) -> None:
        self.sessions: list[object] = []

    async def check_scoped_role(
        self,
        session: object,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        self.sessions.append(session)
        return True


def _database_url(base_url: str, database: str) -> str:
    return make_url(base_url).set(database=database).render_as_string(hide_password=False)


async def test_dashboard_reads_the_reporting_database_not_primary(
    database_url: str, db: Any
) -> None:
    database_name = f"atlas_reporting_test_{uuid4().hex}"
    admin_url = _database_url(database_url, "postgres")
    reporting_url = _database_url(database_url, database_name)

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    primary_engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"), poolclass=NullPool
    )
    reporting_engine = create_async_engine(
        reporting_url.replace("postgresql://", "postgresql+psycopg://"), poolclass=NullPool
    )
    try:
        applied = await asyncio.create_subprocess_exec(
            "psql",
            reporting_url,
            "-v",
            "ON_ERROR_STOP=1",
            "-q",
            "-f",
            str(SCHEMA_SQL),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await applied.communicate()
        assert applied.returncode == 0, stderr.decode()

        group_id, entity_id, project_id = uuid4(), uuid4(), uuid4()
        reporting_factory = async_sessionmaker(reporting_engine, expire_on_commit=False)
        async with reporting_factory() as reporting:
            primary_factory = async_sessionmaker(primary_engine, expire_on_commit=False)
            async with primary_factory() as primary:
                with pytest.raises(ReportingUnavailableError, match="not ready"):
                    await ReportingService(AllowAllIdentity()).get_project_dashboard(
                        primary,
                        reporting,
                        actor_user_id=uuid4(),
                        project_id=project_id,
                    )

            await reporting.execute(
                text(
                    "INSERT INTO organization.business_groups (id, name, status, version) "
                    "VALUES (:id, 'Synthetic Reporting Group', 'active', 1)"
                ),
                {"id": group_id},
            )
            await reporting.execute(
                text(
                    "INSERT INTO organization.legal_entities "
                    "(id, business_group_id, name, status, version) "
                    "VALUES (:id, :group_id, 'Synthetic Reporting Entity', 'active', 1)"
                ),
                {"id": entity_id, "group_id": group_id},
            )
            await reporting.execute(
                text(
                    "INSERT INTO organization.projects "
                    "(id, legal_entity_id, name, code, status, version) "
                    "VALUES (:id, :entity_id, 'Synthetic Replica Project', :code, 'active', 1)"
                ),
                {"id": project_id, "entity_id": entity_id, "code": f"SYN-{project_id}"},
            )
            await reporting.execute(
                text("REFRESH MATERIALIZED VIEW reporting.mv_ceo_project_summary")
            )
            await reporting.commit()

            async with primary_factory() as primary:
                identity = AllowAllIdentity()
                dashboard = await ReportingService(identity).get_project_dashboard(
                    primary,
                    reporting,
                    actor_user_id=uuid4(),
                    project_id=project_id,
                )
                primary_database = await primary.scalar(text("SELECT current_database()"))
                reporting_database = await reporting.scalar(text("SELECT current_database()"))

                assert dashboard.project_id == project_id
                assert identity.sessions == [primary]
                assert primary_database != reporting_database
                assert reporting_database == database_name
    finally:
        await primary_engine.dispose()
        await reporting_engine.dispose()
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
