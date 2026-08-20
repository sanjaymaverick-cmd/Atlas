"""Session token handling.

Blueprint §15: short-lived sessions. ``identity.sessions`` stores
``session_token_hash``, never the token — a database read must not yield
anything usable to impersonate a session, so a leaked backup or a SQL injection
that dumps the table produces hashes and nothing more.

Opaque random tokens rather than JWTs. The session table already carries
``revoked_at`` and ``risk_score``, which is a server-side revocable session; a
JWT is stateless by design and would need a blocklist to support revocation —
which is this table again, with an extra format in front of it.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

TOKEN_BYTES = 32
"""256 bits of entropy. Well beyond guessing, and short enough for a cookie."""

DEFAULT_SESSION_TTL = timedelta(hours=8)
"""A working day. Blueprint §15 calls for short-lived sessions; anything longer
turns an unattended browser into a standing grant."""


def issue_token() -> tuple[str, str]:
    """Mint a session token.

    Returns:
        ``(token, token_hash)``. The token goes to the client once, in an
        httpOnly cookie, and is never stored. The hash is what the session row
        keeps.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    """Hash a session token for storage and lookup.

    Plain SHA-256, deliberately: this is not a password. Tokens are 256 bits of
    machine-generated entropy, so there is no dictionary to attack and nothing
    for a slow KDF to buy — while a slow KDF *would* have to run on every
    request, since lookup is by hash.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(presented: str, stored_hash: str) -> bool:
    """Compare a presented token against a stored hash in constant time.

    ``compare_digest`` rather than ``==`` so response timing does not leak how
    much of a guessed token was correct.
    """
    return hmac.compare_digest(hash_token(presented), stored_hash)


def expiry_from(now: datetime | None = None, ttl: timedelta = DEFAULT_SESSION_TTL) -> datetime:
    return (now if now is not None else datetime.now(UTC)) + ttl


def is_expired(expires_at: datetime, now: datetime | None = None) -> bool:
    if expires_at.tzinfo is None:
        raise ValueError("expires_at must be timezone-aware")
    return expires_at <= (now if now is not None else datetime.now(UTC))
