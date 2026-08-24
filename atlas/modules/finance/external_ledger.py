"""Published provider-neutral boundary for statutory accounting ledgers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExternalLedgerVoucherFact:
    external_id: str
    voucher_type: str
    voucher_number: str
    voucher_date: date
    amount: Decimal
    currency_code: str


@dataclass(frozen=True, slots=True)
class ExternalLedgerPage:
    facts: tuple[ExternalLedgerVoucherFact, ...]
    next_cursor: str | None


class ExternalLedgerError(Exception):
    """Safe boundary error that never includes remote payloads or credentials."""


class ExternalLedger(Protocol):
    async def fetch_submitted_vouchers(
        self, *, company: str, cursor: str | None, page_size: int
    ) -> ExternalLedgerPage: ...
