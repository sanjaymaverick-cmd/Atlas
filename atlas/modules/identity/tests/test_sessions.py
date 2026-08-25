"""Session token tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from atlas.modules.identity.sessions import (
    DEFAULT_SESSION_TTL,
    expiry_from,
    hash_token,
    is_expired,
    issue_token,
    tokens_match,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)


class TestTokenIssuance:
    def test_token_and_hash_correspond(self) -> None:
        token, token_hash = issue_token()
        assert hash_token(token) == token_hash

    def test_tokens_are_unique(self) -> None:
        assert len({issue_token()[0] for _ in range(200)}) == 200

    def test_the_hash_does_not_reveal_the_token(self) -> None:
        """What the database holds must not be usable to authenticate."""
        token, token_hash = issue_token()
        assert token not in token_hash
        assert len(token_hash) == 64  # sha256 hex

    def test_token_has_meaningful_entropy(self) -> None:
        token, _ = issue_token()
        assert len(token) >= 40  # 32 bytes, urlsafe-base64


class TestComparison:
    def test_correct_token_matches(self) -> None:
        token, token_hash = issue_token()
        assert tokens_match(token, token_hash)

    def test_wrong_token_does_not_match(self) -> None:
        _, token_hash = issue_token()
        other, _ = issue_token()
        assert not tokens_match(other, token_hash)

    def test_near_miss_does_not_match(self) -> None:
        token, token_hash = issue_token()
        assert not tokens_match(token[:-1] + ("A" if token[-1] != "A" else "B"), token_hash)


class TestExpiry:
    def test_default_ttl_is_short(self) -> None:
        """Blueprint §15 calls for short-lived sessions."""
        assert DEFAULT_SESSION_TTL <= timedelta(hours=12)

    def test_expiry_is_ttl_from_now(self) -> None:
        assert expiry_from(NOW) == NOW + DEFAULT_SESSION_TTL

    def test_not_expired_before_the_deadline(self) -> None:
        assert not is_expired(NOW + timedelta(seconds=1), now=NOW)

    def test_expired_at_the_deadline(self) -> None:
        assert is_expired(NOW, now=NOW)

    def test_expired_after_the_deadline(self) -> None:
        assert is_expired(NOW - timedelta(seconds=1), now=NOW)

    def test_naive_expiry_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            is_expired(datetime(2026, 8, 17, 12, 0, 0), now=NOW)
