# Staging and UAT configuration

**Status:** application contract ready; host and domain not selected.

Staging must be a persistent, isolated deployment of the same application and
PostgreSQL major version used in production. It must contain synthetic data
only. Do not copy, restore, or anonymise production data into it.

## Required runtime configuration

All values are supplied by the deployment secret/configuration mechanism; none
belong in the repository, image, logs, or CI output.

| Variable | Requirement |
|---|---|
| `ATLAS_DATABASE_URL` | Async PostgreSQL URL for the isolated staging database |
| `ATLAS_WEBAUTHN_RP_ID` | Registrable domain used by the staging browser, without scheme or port |
| `ATLAS_WEBAUTHN_RP_NAME` | Human-readable staging name; defaults to `Atlas` |
| `ATLAS_WEBAUTHN_ORIGIN` | Exact public HTTPS origin, including a non-default port if one is used |

Deployment order:

1. Provision an isolated PostgreSQL 16 database and a least-privilege runtime
   identity.
2. Supply configuration through the selected secrets backend.
3. Run `alembic upgrade head` as a release task.
4. Start `uvicorn atlas.api.application:create_default_app --factory` behind
   the selected TLS reverse proxy.
5. Use `/health/live` for process liveness and `/health/ready` for database
   readiness. Neither endpoint returns connection details.
6. Seed synthetic users and legal entities only through an audited fixture or
   administrative workflow.

## WebAuthn UAT gate

Before release, exercise registration, owner approval, authentication,
revocation, expired/replayed challenge rejection, and cloned-counter handling
on every supported browser/authenticator combination. Evidence must include an
audit-chain verification after the run and confirmation that browser responses,
logs, and monitoring contain no session tokens or credential material.

## Promotion gate

Staging is not production-ready until the owner selects its host/domain, the
key-management backend (§25 item 2), and an operator responsible for migration,
rollback, monitoring, and incident response. Choosing a provider here would
silently close an owner decision, so this repository deliberately does not do
so.
