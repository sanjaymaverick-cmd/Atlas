"""Narrow read-only ERPNext implementation of the External Ledger boundary."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from atlas.modules.finance.external_ledger import (
    ExternalLedgerError,
    ExternalLedgerPage,
    ExternalLedgerVoucherFact,
)

_MAX_PAGE_SIZE = 100


class ERPNextLedgerAdapter:
    """Translate ERPNext responses without exposing Frappe types to Atlas."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch_submitted_vouchers(
        self, *, company: str, cursor: str | None, page_size: int
    ) -> ExternalLedgerPage:
        if not company or len(company) > 140:
            raise ExternalLedgerError("invalid external company reference")
        if not 1 <= page_size <= _MAX_PAGE_SIZE:
            raise ExternalLedgerError("page size is outside the supported range")
        try:
            offset = 0 if cursor is None else int(cursor)
        except ValueError as exc:
            raise ExternalLedgerError("invalid external-ledger cursor") from exc
        if offset < 0:
            raise ExternalLedgerError("invalid external-ledger cursor")

        try:
            response = await self._client.get(
                "/api/resource/Journal Entry",
                params={
                    "fields": '["name","voucher_type","posting_date","total_debit","company"]',
                    "filters": json.dumps(
                        [["docstatus", "=", 1], ["company", "=", company]], separators=(",", ":")
                    ),
                    "limit_start": offset,
                    "limit_page_length": page_size,
                    "order_by": "creation asc,name asc",
                },
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise ExternalLedgerError("external ledger returned an invalid page")
            facts = tuple(self._parse_row(row) for row in rows)
        except ExternalLedgerError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ExternalLedgerError("external ledger request failed") from exc

        next_cursor = str(offset + len(facts)) if len(facts) == page_size else None
        return ExternalLedgerPage(facts=facts, next_cursor=next_cursor)

    @staticmethod
    def _parse_row(value: Any) -> ExternalLedgerVoucherFact:
        if not isinstance(value, dict):
            raise ExternalLedgerError("external ledger returned an invalid voucher")
        try:
            name = str(value["name"])
            voucher_type = str(value["voucher_type"])
            posting_date = date.fromisoformat(str(value["posting_date"]))
            amount = Decimal(str(value["total_debit"]))
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise ExternalLedgerError("external ledger returned an invalid voucher") from exc
        if not name or len(name) > 200 or not voucher_type or len(voucher_type) > 100:
            raise ExternalLedgerError("external ledger returned an invalid voucher")
        if not amount.is_finite() or amount < 0:
            raise ExternalLedgerError("external ledger returned an invalid voucher")
        return ExternalLedgerVoucherFact(
            external_id=name,
            voucher_type=voucher_type,
            voucher_number=name,
            voucher_date=posting_date,
            amount=amount,
            currency_code="INR",
        )
