"""Synthetic contract tests for the read-only ERPNext adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from atlas.modules.finance.erpnext_adapter import ERPNextLedgerAdapter
from atlas.modules.finance.erpnext_connection import (
    ERPNextConnectionConfig,
    create_erpnext_client,
)
from atlas.modules.finance.external_ledger import ExternalLedgerError
from atlas.platform.secrets.base import SecretNotFoundError

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_adapter_normalizes_submitted_vouchers_and_paginates() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/resource/Journal Entry"
        assert request.url.params["limit_start"] == "0"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "name": "SYN-JV-0001",
                        "voucher_type": "Journal Entry",
                        "posting_date": "2026-08-24",
                        "total_debit": "1250.50",
                        "company": "Synthetic Developments",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://erpnext.invalid"
    ) as client:
        adapter = ERPNextLedgerAdapter(
            client, clock=lambda: datetime(2026, 8, 25, 10, 30, tzinfo=UTC)
        )
        page = await adapter.fetch_submitted_vouchers(
            company="Synthetic Developments", cursor=None, page_size=1
        )

    assert page.facts[0].external_id == "SYN-JV-0001"
    assert page.facts[0].amount == Decimal("1250.50")
    assert page.next_cursor is not None
    filters = json.loads(requests[0].url.params["filters"])
    assert filters[-1] == ["creation", "<=", "2026-08-25T10:30:00.000000+00:00"]


@pytest.mark.asyncio
async def test_adapter_cursor_preserves_snapshot_watermark() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "name": f"SYN-JV-{len(requests):04d}",
                        "voucher_type": "Journal Entry",
                        "posting_date": "2026-08-25",
                        "total_debit": "10.00",
                    }
                ]
            },
        )

    clocks = iter(
        [
            datetime(2026, 8, 25, 10, 30, tzinfo=UTC),
            datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
        ]
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://erpnext.invalid"
    ) as client:
        adapter = ERPNextLedgerAdapter(client, clock=lambda: next(clocks))
        first = await adapter.fetch_submitted_vouchers(
            company="Synthetic Developments", cursor=None, page_size=1
        )
        second = await adapter.fetch_submitted_vouchers(
            company="Synthetic Developments", cursor=first.next_cursor, page_size=1
        )

    assert second.next_cursor is not None
    assert requests[1].url.params["limit_start"] == "1"
    assert (
        json.loads(requests[0].url.params["filters"])[-1]
        == json.loads(requests[1].url.params["filters"])[-1]
    )


@pytest.mark.asyncio
async def test_adapter_redacts_remote_failure() -> None:
    remote_payload_sentinel = "synthetic-sensitive-value-must-not-leak"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=remote_payload_sentinel)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://erpnext.invalid"
    ) as client:
        with pytest.raises(ExternalLedgerError) as error:
            await ERPNextLedgerAdapter(client).fetch_submitted_vouchers(
                company="Synthetic Developments", cursor=None, page_size=50
            )

    assert remote_payload_sentinel not in str(error.value)


@pytest.mark.asyncio
async def test_adapter_rejects_unbounded_page_size_without_network() -> None:
    async with httpx.AsyncClient(base_url="https://erpnext.invalid") as client:
        with pytest.raises(ExternalLedgerError, match="page size"):
            await ERPNextLedgerAdapter(client).fetch_submitted_vouchers(
                company="Synthetic Developments", cursor=None, page_size=101
            )


@pytest.mark.asyncio
async def test_adapter_rejects_oversized_response_before_json_parsing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1025)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://erpnext.invalid"
    ) as client:
        with pytest.raises(ExternalLedgerError, match="size limit"):
            await ERPNextLedgerAdapter(client, max_response_bytes=1024).fetch_submitted_vouchers(
                company="Synthetic Developments", cursor=None, page_size=50
            )


class SecretsStub:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, name: str) -> str:
        try:
            return self.values[name]
        except KeyError as exc:
            raise SecretNotFoundError(name) from exc

    def get_optional(self, name: str, default: str | None = None) -> str | None:
        return self.values.get(name, default)


@pytest.mark.asyncio
async def test_connection_injects_secret_auth_and_refuses_redirects() -> None:
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"data": []})

    config = ERPNextConnectionConfig(base_url="https://erpnext.invalid")
    secrets = SecretsStub(
        {"erpnext-api-key": "synthetic-key", "erpnext-api-secret": "synthetic-value"}
    )
    async with create_erpnext_client(
        config, secrets, transport=httpx.MockTransport(handler)
    ) as client:
        await client.get("/api/resource/Company")

    assert observed[0].headers["Authorization"] == "token synthetic-key:synthetic-value"
    assert client.follow_redirects is False


@pytest.mark.asyncio
async def test_connection_requires_https_except_explicit_local_development() -> None:
    secrets = SecretsStub(
        {"erpnext-api-key": "synthetic-key", "erpnext-api-secret": "synthetic-value"}
    )
    with pytest.raises(ExternalLedgerError, match="HTTPS"):
        create_erpnext_client(ERPNextConnectionConfig(base_url="http://erpnext.invalid"), secrets)

    client = create_erpnext_client(
        ERPNextConnectionConfig(base_url="http://127.0.0.1:8001", allow_insecure_localhost=True),
        secrets,
    )
    assert client.base_url == httpx.URL("http://127.0.0.1:8001")
    await client.aclose()
