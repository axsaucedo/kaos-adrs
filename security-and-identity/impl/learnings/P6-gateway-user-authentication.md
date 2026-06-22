# P6 — Gateway user authentication (learnings)

**Phase**: P6 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Date**: 2026-06-22
**Context**: adding the human-identity half of the two-identity model — operator-generated Envoy `jwt_authn` providers (agent required, user optional) ahead of `ext_authz`, plus a CLI Keycloak install with a non-interactive realm bootstrap. Validated live on `kind-kaos-e2e` against Envoy Gateway v1.4.6.

## Key findings

### Envoy Gateway multi-provider JWT is `requires_any` (OR), gated by a single policy-level `optional`

EG v1.4.6 `SecurityPolicy.spec.jwt` exposes a list of `providers` and a single boolean `optional` (default `false`); there is **no per-provider "required" flag**. The CRD documents — and the cluster confirms — that "the JWT is considered valid if **any** of the providers successfully validate". So with two providers and `optional` left at its default, a request passes iff it carries at least one token that validates against some provider, and is rejected (401) only when no provider validates. This maps cleanly onto KAOS's needs because the **agent actor token is always present on a protected call**: the agent provider always satisfies the "≥1 valid token" gate, the autonomous (actor-only) path passes with no user token, and the user provider simply validates the human subject when it is present. No `spec.jwt.optional` override is needed.

### "Optional user" means an invalid user token is ignored, not rejected

The original plan expected `valid agent + invalid user → reject`. Empirically (EG v1.4.6) that case returns **200**: `requires_any` short-circuits as soon as the agent provider succeeds, and the invalid token sitting in the user provider's extraction slot is neither validated nor allowed to fail the request. Critically, because the user provider did **not** run, it injects **no** `x-user-claim-*` headers — so the invalid token is *ignored*, never *trusted*. This is the correct optional-JWT semantic: an attacker cannot manufacture a verified user identity by presenting a garbage user token; they can only fail to add one. The observed matrix:

| request | status |
|---|---|
| valid agent only, no user | 200 |
| valid agent + invalid user | 200 (invalid user ignored, no user claims injected) |
| no tokens | 401 |
| valid user only, no agent | 200 at jwt (then `ext_authz` rejects on missing actor) |
| valid agent + valid user | 200 |
| garbage agent only | 401 |

### A non-running provider does not sanitize its claim-to-header outputs — strip them before trusting

The sharpest finding. Envoy's `claim_to_headers` clears and overwrites the configured header **only when that provider validates a token**. With a valid agent token, a forged inbound `x-agent-claim-sub` is overwritten by the verified claim (the agent provider always runs) — safe. But a forged inbound `x-user-claim-sub` **passes through unchanged** on an actor-only request, because the user provider did not run and therefore never sanitized its header. P6 is safe today only because the operator sets `headersToExtAuth: [authorization, x-agent-authorization]`, so the user claim headers are **not** forwarded to `ext_authz`, and the authorization decision keys on the sanitized agent actor. The moment a downstream consumer (P7 token exchange / delegation) starts trusting `x-user-claim-*`, the gateway **must** strip inbound `x-agent-claim-*`/`x-user-claim-*` at ingress (or only trust a claim header when its provider validated). This is a hard P7 prerequisite, not a P6 gap in the actor decision.

### JWKS reachability and issuer canonicalisation are separate concerns — and both bite

Envoy validates the token's `iss` claim against the provider's `issuer` string **exactly**, and fetches keys from `remoteJWKS.uri` independently. Keycloak stamps `iss` from the request's front-end host, so a token minted through a host port-forward (`iss=http://localhost:8080/...`) is rejected by a provider configured with the in-cluster issuer even though the JWKS fetch succeeds. The fix for validation is to mint tokens the same way production does — **in-cluster**, so `iss` is the canonical service URL the provider expects. The operator therefore derives the JWKS URI from the issuer (AIB: `<issuer>/oauth2/jwks.json`; Keycloak/OIDC realm: `<issuer>/protocol/openid-connect/certs`) and always allows an explicit `jwksUri` override, since it cannot fetch `.well-known/openid-configuration` at template time.

### A Keycloak realm-import user must be marked "fully set up" or the password grant fails

The non-interactive token recipe is the OAuth2 password (Direct Access Grant) flow against a confidential client with `directAccessGrantsEnabled: true` and an `oidc-audience-mapper` (so the access token carries the audience the gateway verifies). The trap: an imported user created with only `username`/`enabled`/`credentials` is rejected at token time with `invalid_grant: "Account is not fully set up"`. The user must also carry `emailVerified: true`, an `email`, and an empty `requiredActions: []` so Keycloak considers the account complete and issues a token immediately. Found and fixed live.

### Self-contained Keycloak (`start-dev`, H2) is the simplest dev/e2e install

Third-party Keycloak charts (Bitnami, codecentric) pull in external-DB assumptions that fight a throwaway KIND validation. Running the official image with `start-dev --import-realm`, H2 in-memory and no DB — a two-object Deployment + Service applied via kubectl, with the realm delivered as an `--import-realm` ConfigMap — is the smallest thing that imports a realm and serves JWKS. The CLI keeps a `--keycloak-chart-path` Helm override for environments that want a managed chart, mirroring the broker dev path, but the default needs no chart at all.

### The user provider is admin-surface config, so it keeps the `SECURITY_*_AUTH_*` prefix

The recent pod-credential rename moved agent **pod** credentials to the provider-agnostic `AGENT_AUTH_*` prefix. The operator/admin configuration surface is a different thing and stays `SECURITY_*_AUTH_*`; P6's new config is admin surface, so it is `SECURITY_USER_AUTH_*`, consistent with the existing `SECURITY_AGENT_AUTH_*`. Keeping the two surfaces distinct avoids conflating "what an agent pod reads to fetch its own token" with "what the operator is told about the issuers it must wire into the gateway".

## Locked configuration (reference)

- **EG version**: `docker.io/envoyproxy/gateway:v1.4.6`.
- **`spec.jwt` shape**: two providers; agent extracts `x-agent-authorization` (`valuePrefix: "Bearer "`), user uses default `Authorization` extraction with `audiences`; each maps claims to `x-agent-claim-*`/`x-user-claim-*`; `spec.jwt.optional` left default (`false`). No requirement override needed.
- **Keycloak token recipe**: `POST <issuer>/protocol/openid-connect/token`, `grant_type=password`, confidential client `kaos` (secret), `scope=openid`; realm user fully set up; audience mapper emits `aud=kaos`. Mint in-cluster so `iss` matches the provider.
