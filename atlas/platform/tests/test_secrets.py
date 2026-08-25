"""Secrets provider tests.

The guard against running outside development is the important one. An
environment-backed secrets provider is fine for local work and unacceptable in
production, and the difference must not come down to somebody remembering.
"""

from __future__ import annotations

import pytest

from atlas.platform.secrets.base import SecretNotFoundError, SecretsProvider
from atlas.platform.secrets.env_provider import EnvSecretsProvider

pytestmark = pytest.mark.unit


class TestEnvironmentGuard:
    @pytest.mark.parametrize("environment", ["development", "test"])
    def test_permitted_in_development_and_test(self, environment: str) -> None:
        assert EnvSecretsProvider(environment, source={}) is not None

    @pytest.mark.parametrize("environment", ["production", "staging", "uat", ""])
    def test_refused_everywhere_else(self, environment: str) -> None:
        """Fails at construction, not at first use.

        A service that starts and only fails when it needs a secret has already
        accepted traffic by then.
        """
        with pytest.raises(RuntimeError, match="not permitted in environment"):
            EnvSecretsProvider(environment, source={})

    def test_the_refusal_says_what_to_do(self) -> None:
        with pytest.raises(RuntimeError, match="Blueprint"):
            EnvSecretsProvider("production", source={})


class TestLookup:
    def test_reads_a_prefixed_variable(self) -> None:
        provider = EnvSecretsProvider("test", source={"ATLAS_SECRET_DATABASE_PASSWORD": "hunter2"})
        assert provider.get("database_password") == "hunter2"

    @pytest.mark.parametrize(
        "name", ["database_password", "DATABASE_PASSWORD", "database-password"]
    )
    def test_name_normalisation(self, name: str) -> None:
        provider = EnvSecretsProvider("test", source={"ATLAS_SECRET_DATABASE_PASSWORD": "hunter2"})
        assert provider.get(name) == "hunter2"

    def test_dotted_names_normalise(self) -> None:
        provider = EnvSecretsProvider("test", source={"ATLAS_SECRET_DB_PASSWORD": "x"})
        assert provider.get("db.password") == "x"

    def test_missing_secret_raises(self) -> None:
        provider = EnvSecretsProvider("test", source={})
        with pytest.raises(SecretNotFoundError):
            provider.get("nope")

    def test_the_error_names_the_variable_expected(self) -> None:
        provider = EnvSecretsProvider("test", source={})
        with pytest.raises(SecretNotFoundError, match="ATLAS_SECRET_SIGNING_KEY"):
            provider.get("signing_key")

    def test_optional_returns_default(self) -> None:
        provider = EnvSecretsProvider("test", source={})
        assert provider.get_optional("absent", "fallback") == "fallback"
        assert provider.get_optional("absent") is None

    def test_optional_prefers_the_real_value(self) -> None:
        provider = EnvSecretsProvider("test", source={"ATLAS_SECRET_TOKEN": "real"})
        assert provider.get_optional("token", "fallback") == "real"

    def test_an_unprefixed_variable_is_not_a_secret(self) -> None:
        """Only ATLAS_SECRET_* counts, so arbitrary environment is not readable."""
        provider = EnvSecretsProvider("test", source={"DATABASE_PASSWORD": "leaked"})
        with pytest.raises(SecretNotFoundError):
            provider.get("database_password")


class TestProtocolConformance:
    def test_env_provider_satisfies_the_protocol(self) -> None:
        """Swapping in Vault or a cloud KMS later means implementing this."""
        provider = EnvSecretsProvider("test", source={})
        assert isinstance(provider, SecretsProvider)
