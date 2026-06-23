# P9 — SDK token lifecycle (progress)

**Phase**: P9 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P9-sdk-token-lifecycle.md`](../../plan/P9-sdk-token-lifecycle.md)
**Status**: Complete — the agent runtime now owns a managed actor-token lifecycle. When the operator mounts broker credentials, the SDK mints this agent's actor token via the OAuth2 `client_credentials` grant, refreshes it ahead of expiry, reloads a rotated client secret from its mounted file, injects the token on outbound A2A/MCP/ModelAPI calls, and transparently refreshes-and-replays once on a gateway `401`. A static actor token and any caller-supplied actor header still take precedence, and everything is inert when no credentials are present.
**Date**: 2026-06-22
**PR**: stacked onto `feat/crd-identity-override` (the P8 branch)

## Outcome

Before P9 an agent's actor token was a static value — either configured on the pod (`AGENT_AUTH_TOKEN` / `security.actorToken`) or absent. There was no way for the runtime to obtain its own token, no refresh, and no recovery when a token expired or a credential rotated. P9 adds a self-contained token lifecycle to the AIB SDK so the agent authenticates as itself without operator-side token plumbing:

- **Mint**: `ActorTokenManager` performs the `client_credentials` grant against `AGENT_AUTH_TOKEN_ENDPOINT` using `AGENT_AUTH_CLIENT_ID` + the client secret, caching the result.
- **Refresh-ahead**: the token is proactively refreshed at `lifetime * (1 - refresh_fraction)` (default 80% of its life) so an in-flight request never races expiry; single-flight locks (`threading.Lock` / `asyncio.Lock`) collapse concurrent refreshes.
- **Rotation reload**: the client secret is sourced file-first from the mounted `AGENT_AUTH_CLIENT_SECRET_FILE`, re-read on mtime change, falling back to `AGENT_AUTH_CLIENT_SECRET`; an `invalid_client` / `401` during a grant reloads the credential and retries.
- **Inject**: outbound instrumentation injects the managed token when the request carries no actor token, additively (never overwriting a caller-supplied header), using a non-blocking async acquisition on the async path.
- **Reactive recovery**: an instrumented request that carried an actor token and gets a `401` triggers a single forced refresh + replay.
- **Fail-closed**: when no valid token can be obtained the SDK raises `AIBUnavailable` rather than sending an unauthenticated request; a still-valid cached token is served if a refresh fails.

An optional off-gateway `Client` / `AsyncClient` is also added for callers that operate outside the gateway and want to ask the broker directly for an access decision or a delegated token.

## Deliverables

| Area | Deliverable |
|---|---|
| Managed lifecycle | `pydantic-ai-server/aib/identity.py` — `ActorTokenManager` (`token`/`token_async`/`force_refresh`/`force_refresh_async`/`invalidate`, single-flight, refresh-ahead, bounded backoff, fail-closed serving a still-valid cache), `_Credential` (file-first + mtime reload + env fallback), `instrument_agent_identity(...)` reading the provider-agnostic `AGENT_AUTH_*` env, module accessors `actor_token`/`actor_token_async`/`get_manager`/`reset_manager`, `AIBUnavailable`. |
| Credential rotation | `_Credential` re-reads the mounted secret file only on mtime change and reloads on an `invalid_client`/`401` grant failure; wired through `AGENT_AUTH_CLIENT_SECRET_FILE` (or an explicit `client_secret_file`). |
| Reactive 401 retry | `pydantic-ai-server/aib/instrument.py` — `instrument_httpx` refreshes the actor token once and replays the request on a `401` (sync + async) when a managed identity is active and the request carried `x-agent-authorization`. |
| Outbound injection | `instrument.py` — outbound injection falls back to the managed actor token when the context carries none, additive, with a non-blocking async acquisition; `ctx.get()` accessor added. |
| Off-gateway client | `pydantic-ai-server/aib/client.py` — `Client`/`AsyncClient` with `check_access`/`require_access` (structured `AccessDecision`) and `exchange_token`/`get_token` (RFC 8693 → `TokenResult`); `AccessDenied`/`ReauthenticationRequired` for deny vs recoverable-reauth; principal/actor/request-id default from `aib.ctx`; transport failures → `AIBUnavailable`. |
| Operator credential mount | `operator/controllers/agent_controller.go` — when credential mounting is enabled, the per-agent credential Secret is projected read-only at `/var/run/aib` and `AGENT_AUTH_CLIENT_SECRET_FILE=/var/run/aib/client_secret` is exported; the existing `client_secret` SecretKeyRef env stays as a startup fallback. `operator/pkg/security/config.go` — `CredentialMountDir`/`CredentialSecretKey`/`CredentialSecretFilePath` helpers. |
| Runtime wiring | `pydantic-ai-server/pais/server.py` — `instrument_agent_identity()` is set up when no static actor token is configured, so the managed token is minted and injected on outbound calls. |

## Validation

- **SDK unit tests**: `pydantic-ai-server/tests/test_aib_identity.py` (acquire/refresh-ahead/cache/fail-closed, file secret source + mtime reload + env fallback, `invalid_client` reload-and-retry, async mint, reactive `401` refresh+replay sync/async, managed-token injection sync/async, no-override of a caller header, no-manager inert) and `tests/test_aib_client.py` (allow/deny/reauth decisions, ctx-sourced actor/principal headers, RFC 8693 exchange, `get_token` from ctx subject token, transport-error → `AIBUnavailable`, async path). 61 aib tests green; full Python suite green; `black --check` clean; new files `ty`-clean (only pre-existing `server.py`/`tools.py` diagnostics from local-ty version skew remain).
- **Operator unit tests**: `go test ./pkg/... ./controllers/...` green incl. the new credential-volume + `AGENT_AUTH_CLIENT_SECRET_FILE` assertions and the disabled-path test; `go build ./...` clean. No CRD schema change, so manifests are unaffected. (`make test-unit` still hits the local go1.26-vs-go1.25 coverage recompile mismatch — environmental.)
- **Real-network lifecycle check**: a scratch harness ran the manager against a live local token endpoint and proved mint → cache (no re-mint) → rotated-secret reload on `force_refresh` → fail-closed `AIBUnavailable` against a dead endpoint → no-identity inert (`instrument_agent_identity` returns `None` with no creds). All passed.
- **Full auth-enabled e2e** (managed mint end-to-end, rotation, 401 recovery, fail-closed, no-identity regression): exercised in CI on the stacked PR; locally gated on building+loading new operator/agent images, deferred to CI per the efficiency policy.

## Notes

- **Plan env names were stale** — the P9 plan text used `AIB_*`; the operator and SDK use the provider-agnostic `AGENT_AUTH_*` (`IDENTITY`/`TOKEN`/`PRINCIPAL`/`CLIENT_ID`/`CLIENT_SECRET`/`TOKEN_ENDPOINT`/`ISSUER`/`BASE_URL`), with `AGENT_AUTH_CLIENT_SECRET_FILE` for the mounted secret. The minted actor token's subject is the broker client derived from `AGENT_AUTH_CLIENT_ID`, which the operator sets from the P8-resolved identity (honouring `spec.security.id`).
- **The off-gateway client is a convenience, not the enforcement boundary** — gateway traffic is still authorized by ext_authz and exchanged by ext_proc. The client is for processes that talk to the broker directly.
