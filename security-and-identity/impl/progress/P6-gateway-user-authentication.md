# P6 — Gateway user authentication (progress)

**Phase**: P6 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P6-gateway-user-authentication.md`](../../plan/P6-gateway-user-authentication.md)
**Status**: Complete — the operator now generates Envoy `jwt_authn` providers (agent + optional user) ahead of `ext_authz`, the CLI installs a Keycloak user identity provider with a bootstrapped realm, and the combined gateway path was validated live on local KIND against Envoy Gateway v1.4.6.
**Date**: 2026-06-22
**PR**: stacked onto `feat/sync-service-reconciliation` (the P5 branch)

## Outcome

Before P6 the gateway enforced only `ext_authz` (the agent actor → resource decision) and validated no JWT cryptographically. P6 adds the human-identity half of the two-identity model: the operator emits two `jwt_authn` providers on protected `SecurityPolicy` resources — an **agent** provider that verifies the broker-issued actor token carried on `x-agent-authorization`, and an **optional user** provider that verifies the human subject token on the standard `Authorization` header — both running before the unchanged `ext_authz` block. The CLI gains a Keycloak install with a non-interactive realm bootstrap (confidential direct-access-grant client, audience mapper, fully-set-up test user) and wires `security.userAuth` into the operator. The whole path is opt-in: with no issuers configured the `jwt` block is not rendered and default installs are byte-for-byte unchanged.

## Deliverables

| Area | Deliverable |
|---|---|
| Operator config | `pkg/security/config.go` — `UserIssuer`/`UserAudience`/`UserJWKSURIOverride` fields + `SECURITY_USER_AUTH_ISSUER`/`_AUDIENCE`/`_JWKS_URI` env; `JWTEnabled()` (agent or user issuer set), `AgentJWKSURI()` (derives `<issuer>/oauth2/jwks.json`), `UserJWKSURI()` (explicit override else `<issuer>/protocol/openid-connect/certs`). `IsOperational()` unchanged (still keys on `ExtAuthzURL`). |
| SecurityPolicy | `pkg/security/securitypolicy.go` — `constructJWTProviders(cfg)` emits `spec.jwt.providers` when `JWTEnabled()`: agent provider (issuer, remoteJWKS, `extractFrom` `x-agent-authorization` `Bearer `, `claimToHeaders` sub→`x-agent-claim-sub`), user provider emitted only when a user issuer is set (issuer, remoteJWKS, optional `audiences`, default `Authorization` extraction, `claimToHeaders` sub/preferred_username). `extAuth` block and `headersToExtAuth` unchanged. |
| Operator chart | `chart/values.yaml` `security.userAuth` block (issuer/audience/jwksUri, empty default); `templates/operator-configmap.yaml` renders `SECURITY_USER_AUTH_*` only-when-set, mirroring `agentAuth`. |
| CLI | `kaos_cli/install.py` — `_install_keycloak` (self-contained dev deployment: `start-dev`, H2 in-memory, no DB, `--import-realm`; or Helm when `--keycloak-chart-path` is given), `_bootstrap_keycloak_realm` (realm-import ConfigMap via kubectl), `_default_user_auth_issuer`, `_build_auth_operator_args` extended with `security.userAuth.*`. New flags `--user-auth/--no-user-auth` (default on under `--auth-enabled`), `--keycloak-namespace`, `--keycloak-chart-path`, `--user-auth-issuer`, `--user-auth-audience`. |
| Token helper | Non-interactive Keycloak user-token minting helper (password/direct-access grant) with decode-and-assert of `iss`/`aud`, used for e2e validation. |

## Validation

- **Operator unit tests**: `go test ./pkg/security/...` green — config parsing, `JWTEnabled()` (agent-only/user-only/both/neither), JWKS resolution (explicit vs derived), and SecurityPolicy emission (both providers / agent-only / no-jwt-when-disabled / `extAuth` unchanged). `gofmt`/`go vet` clean; `make manifests generate` no drift.
- **Chart**: `helm template` renders `SECURITY_USER_AUTH_*` when set and nothing when absent; `helm lint` clean.
- **CLI**: 79 tests green (incl. new user-auth operator wiring, Keycloak install args, realm ConfigMap + dev deployment, `--no-user-auth` omission, `--keycloak-chart-path` Helm path).
- **Live on KIND (`kind-kaos-e2e`, Envoy Gateway v1.4.6)**: installed Keycloak via the new CLI path (realm `kaos` imported, pod Ready), minted a real user token in-cluster (`iss` = in-cluster realm URL, `aud` = `kaos`), and drove the gateway with a two-provider `SecurityPolicy` to confirm the optionality matrix and claim-header sanitization (see learnings). The hand-applied `SecurityPolicy` is byte-equivalent to `constructJWTProviders` output and was accepted and enforced by EG.

## Notes

- The full installer-driven combined path (operator-generated `SecurityPolicy` on a live `Agent → MCPServer` with AIB `ext_authz` after `jwt_authn`, using an AIB-minted actor token) remains local-KIND only while the broker is unpublished. The running operator predates the jwt change, so the on-cluster validation exercised the exact generated jwt shape independently (hand-applied, EG-accepted, functionally enforced) while `ext_authz` itself is unchanged from P3 and validated there. The security e2e lane (local-KIND) is where the rebuilt-operator end-to-end run belongs.
- A claim-header spoofing nuance was found and is documented in learnings: an optional provider that does not run does not sanitize its `claimToHeaders` outputs, so inbound `x-user-claim-*` headers pass through. P6 is safe because `headersToExtAuth` forwards only `authorization` + `x-agent-authorization` (the sanitized agent actor drives the decision); stripping/trusting user claim headers is a P7 prerequisite.
- Out of scope (later phases): `ext_proc` token exchange and user-delegated third-party grants (P7); `spec.security.id` CRD identity override (P8); interactive browser SSO; fine-grained user RBAC.
