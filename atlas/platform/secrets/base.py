"""Secrets access boundary.

Blueprint §3.3 and §15.1 require application secrets to come from a dedicated
secrets manager rather than configuration files. Which product — self-hosted
Vault, a cloud KMS, an HSM — is an open owner decision (§25 item 2) and is not
resolved here.

This module is how Phase 1 proceeds without that decision blocking it: every
consumer depends on the ``SecretsProvider`` protocol, never on a concrete
backend and never on ``os.environ`` directly. Choosing a product later means
adding one implementation class and changing one line of wiring in
``atlas/main.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class SecretNotFoundError(KeyError):
    """Raised when a required secret is absent.

    Deliberately fatal rather than falling back to a default: a service that
    silently starts without its real signing key is worse than one that refuses
    to start.
    """


@runtime_checkable
class SecretsProvider(Protocol):
    """Read-only access to named secrets.

    Read-only by design. Rotation is an operational action performed against
    the backing store under audit, not something the application performs on
    itself at runtime.
    """

    def get(self, name: str) -> str:
        """Return the secret's value, or raise ``SecretNotFoundError``."""
        ...

    def get_optional(self, name: str, default: str | None = None) -> str | None:
        """Return the secret's value, or ``default`` when it is absent."""
        ...
