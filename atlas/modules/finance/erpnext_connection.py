"""Secure construction boundary for the read-only ERPNext HTTP client."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from atlas.modules.finance.external_ledger import ExternalLedgerError
from atlas.platform.secrets.base import SecretsProvider

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_DEFAULT_AUTH_IDENTIFIER_REFERENCE = "erpnext-api-key"
_DEFAULT_AUTH_MATERIAL_REFERENCE = "erpnext-api-secret"


@dataclass(frozen=True, slots=True)
class ERPNextConnectionConfig:
    base_url: str
    auth_identifier_reference: str = _DEFAULT_AUTH_IDENTIFIER_REFERENCE
    auth_material_reference: str = _DEFAULT_AUTH_MATERIAL_REFERENCE
    allow_insecure_localhost: bool = False
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 20.0
    max_connections: int = 10
    max_response_bytes: int = 2 * 1024 * 1024

    def validate(self) -> None:
        parsed = urlsplit(self.base_url)
        is_local_http = (
            parsed.scheme == "http"
            and parsed.hostname in _LOCAL_HOSTS
            and self.allow_insecure_localhost
        )
        if parsed.scheme != "https" and not is_local_http:
            raise ExternalLedgerError("ERPNext base URL must use HTTPS")
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ExternalLedgerError("ERPNext base URL is invalid")
        if (
            self.connect_timeout_seconds <= 0
            or self.read_timeout_seconds <= 0
            or not 1 <= self.max_connections <= 100
            or not 1024 <= self.max_response_bytes <= 10 * 1024 * 1024
        ):
            raise ExternalLedgerError("ERPNext connection limits are invalid")


def create_erpnext_client(
    config: ERPNextConnectionConfig,
    secrets: SecretsProvider,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Build a non-redirecting, bounded client from secret references."""

    config.validate()
    api_key = secrets.get(config.auth_identifier_reference)
    api_secret = secrets.get(config.auth_material_reference)
    if (
        not api_key
        or not api_secret
        or "\r" in api_key + api_secret
        or "\n" in api_key + api_secret
    ):
        raise ExternalLedgerError("ERPNext credentials are invalid")
    return httpx.AsyncClient(
        base_url=config.base_url,
        headers={
            "Authorization": f"token {api_key}:{api_secret}",
            "Accept": "application/json",
            "User-Agent": "atlas-external-ledger/1",
        },
        timeout=httpx.Timeout(
            connect=config.connect_timeout_seconds,
            read=config.read_timeout_seconds,
            write=config.read_timeout_seconds,
            pool=config.connect_timeout_seconds,
        ),
        limits=httpx.Limits(
            max_connections=config.max_connections,
            max_keepalive_connections=config.max_connections,
        ),
        follow_redirects=False,
        transport=transport,
    )
