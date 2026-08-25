"""Narrow read-only ERPNext implementation of the External Ledger boundary."""

from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from atlas.modules.finance.external_ledger import (
    ExternalLedgerError,
    ExternalLedgerPage,
    ExternalLedgerVoucherFact,
)

_MAX_PAGE_SIZE = 100
_DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ERPNextLedgerAdapter:
    """Translate ERPNext responses without exposing Frappe types to Atlas."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if not 1024 <= max_response_bytes <= 10 * 1024 * 1024:
            raise ExternalLedgerError("external-ledger response limit is invalid")
        self._client = client
        self._max_response_bytes = max_response_bytes
        self._clock = clock

    async def fetch_submitted_vouchers(
        self, *, company: str, cursor: str | None, page_size: int
    ) -> ExternalLedgerPage:
        if not company or len(company) > 140:
            raise ExternalLedgerError("invalid external company reference")
        if not 1 <= page_size <= _MAX_PAGE_SIZE:
            raise ExternalLedgerError("page size is outside the supported range")
        watermark, offset = self._decode_cursor(cursor)

        try:
            async with self._client.stream(
                "GET",
                "/api/resource/Journal Entry",
                params={
                    "fields": '["name","voucher_type","posting_date","total_debit","company"]',
                    "filters": json.dumps(
                        [
                            ["docstatus", "=", 1],
                            ["company", "=", company],
                            ["creation", "<=", watermark],
                        ],
                        separators=(",", ":"),
                    ),
                    "limit_start": offset,
                    "limit_page_length": page_size,
                    "order_by": "creation asc,name asc",
                },
            ) as response:
                response.raise_for_status()
                declared_length = response.headers.get("content-length")
                if declared_length is not None and int(declared_length) > self._max_response_bytes:
                    raise ExternalLedgerError("external ledger response exceeded the size limit")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > self._max_response_bytes:
                        raise ExternalLedgerError(
                            "external ledger response exceeded the size limit"
                        )
            payload = json.loads(content)
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise ExternalLedgerError("external ledger returned an invalid page")
            facts = tuple(self._parse_row(row) for row in rows)
        except ExternalLedgerError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, OverflowError) as exc:
            raise ExternalLedgerError("external ledger request failed") from exc

        next_cursor = (
            self._encode_cursor(watermark, offset + len(facts)) if len(facts) == page_size else None
        )
        return ExternalLedgerPage(facts=facts, next_cursor=next_cursor)

    def _decode_cursor(self, cursor: str | None) -> tuple[str, int]:
        if cursor is None:
            current = self._clock().astimezone(UTC)
            return current.isoformat(timespec="microseconds"), 0
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            value = json.loads(urlsafe_b64decode(padded.encode("ascii")))
            watermark = datetime.fromisoformat(value["watermark"])
            offset = int(value["offset"])
        except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise ExternalLedgerError("invalid external-ledger cursor") from exc
        if watermark.tzinfo is None or offset < 0 or offset > 1_000_000_000:
            raise ExternalLedgerError("invalid external-ledger cursor")
        normalized = watermark.astimezone(UTC).isoformat(timespec="microseconds")
        return normalized, offset

    @staticmethod
    def _encode_cursor(watermark: str, offset: int) -> str:
        payload = json.dumps(
            {"watermark": watermark, "offset": offset}, separators=(",", ":"), sort_keys=True
        )
        return urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

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
