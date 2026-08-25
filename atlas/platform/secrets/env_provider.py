"""Environment-backed secrets provider — local development and test only.

This is the Phase 1 concrete implementation behind ``SecretsProvider``. It is
deliberately the least capable option that still lets the rest of the system be
written against the real interface: no rotation, no access logging, no
per-service scoping. Those arrive with whichever product closes Blueprint §25
item 2.

It refuses to run outside development so it cannot become the production
default by inattention.
"""

from __future__ import annotations

import os

from atlas.platform.secrets.base import SecretNotFoundError

_PREFIX = "ATLAS_SECRET_"


class EnvSecretsProvider:
    """Reads secrets from ``ATLAS_SECRET_*`` environment variables.

    Args:
        environment: The deployment environment name. Anything other than
            ``development`` or ``test`` raises, because this provider stores
            secrets in the process environment where they are visible to
            anything that can read ``/proc``.
        source: Mapping to read from. Defaults to ``os.environ``; injectable
            so tests need not mutate global process state.
    """

    def __init__(
        self,
        environment: str,
        source: dict[str, str] | None = None,
    ) -> None:
        if environment not in ("development", "test"):
            raise RuntimeError(
                f"EnvSecretsProvider is not permitted in environment {environment!r}. "
                "Configure a real secrets backend (Blueprint §3.3, §25 item 2) "
                "before deploying outside development."
            )
        self._source = source if source is not None else dict(os.environ)

    @staticmethod
    def _key(name: str) -> str:
        return f"{_PREFIX}{name.upper().replace('-', '_').replace('.', '_')}"

    def get(self, name: str) -> str:
        value = self._source.get(self._key(name))
        if value is None:
            raise SecretNotFoundError(
                f"secret {name!r} not found (expected environment variable {self._key(name)})"
            )
        return value

    def get_optional(self, name: str, default: str | None = None) -> str | None:
        return self._source.get(self._key(name), default)
