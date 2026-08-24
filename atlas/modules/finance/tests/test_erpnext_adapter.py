"""Synthetic contract tests for the read-only ERPNext adapter."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from atlas.modules.finance.erpnext_adapter import ERPNextLedgerAdapter
from atlas.modules.finance.external_ledger import ExternalLedgerError

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_adapter_normalizes_submitted_vouchers_and_paginates() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
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
        page = await ERPNextLedgerAdapter(client).fetch_submitted_vouchers(
            company="Synthetic Developments", cursor=None, page_size=1
        )

    assert page.facts[0].external_id == "SYN-JV-0001"
    assert page.facts[0].amount == Decimal("1250.50")
    assert page.next_cursor == "1"


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
