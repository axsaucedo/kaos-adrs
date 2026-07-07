# ADR 0002 — Identity and authentication

- **Status.** Proposed
- **Date.** 2026-07-07
- **Component.** 2 of 4 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md), [research/007](../research/007-user-token-propagation-idp-sidecar-and-future-deep-dives.md), [target-picture/007](../target-picture/007-decision-identity-model-and-source-of-truth.md), [model-parity learnings](../impl/learnings/opa-extproc-authz-model-parity-and-oauth-path.md)
- **Resolved by.** [ADR 0003](./adr_0003_authorization-models-and-policy-data.md) (how identities key the grant facts)

## Context

The gateway authorizes on two identities: the **user** on whose behalf a request runs, and the **agent** carrying it. KAOS already mints a per-agent actor token in the runtime (`pydantic-ai-server/aib/identity.py`) via OAuth2 `client_credentials` and injects both an `authorization` (subject) header and an `x-agent-authorization` (actor) header (`instrument.py`). The user subject token comes from a standard OIDC provider (Keycloak) and is already validated at the gateway by the existing JWT authn. This ADR settles the identity contract that threads the whole system and the trust model for each token. It does not decide the authorization models that consume these identities ([ADR 0003](./adr_0003_authorization-models-and-policy-data.md)).

## Decision

### One logical identity threads everything

A single logical identity string identifies an agent everywhere it appears: `kaos://agent/<namespace>/<name>` is simultaneously the agent's AIB `external_id`, its OPA data key, and the `sub` claim of its actor token (`AGENT_AUTH_IDENTITY`). Resources use the parallel form `kaos://<kind-slug>/<namespace>/<name>` as the AIB service id and the OPA resource value. This one identity makes Model 1 and Model 2 interchangeable at the data layer and keeps grants auditable and stable across redeploys. **Verify at implementation** (do not assume): confirm the broker stamps the `client_credentials` token `sub` as the logical identity rather than an internal UUID; if it stamps a UUID, key Model-1 data by UUID or carry a UUID→logical map in the data.

### Two token dimensions: subject and actor

The **subject** (user) token is a Keycloak-issued OIDC token, already validated at the gateway by the standard `Authorization` JWT authn. The **actor** (agent) token is an AIB-issued JWT minted via `client_credentials`, carried in the custom `x-agent-authorization` header. Both are decoded into the OPA input ([ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md)); enforcement keys on both plus the requested resource.

### Actor-token authentication is real, not header-trust

The actor token is a genuinely signed JWT minted against AIB/Keycloak, not a self-asserted header. The proof-of-concept rego used `io.jwt.decode` (no signature verification) as an explicit shortcut, and nothing in ext_proc validates the actor header today. A production posture **must verify** the actor token's signature, issuer, and expiry before trusting its `sub`. Because the subject token is already gateway-verified, only the actor token needs added verification.

### Verification is optional and config-gated: demo vs verified

Verification is a gradient controlled by whether an issuer is configured, mirroring the existing issuer-presence gating:

- **No issuer configured — demo mode.** The gateway renders no JWT authn, the operator injects no JWKS, and the rego uses `io.jwt.decode` (header-trust). Coarse route/agent authorization works with **no Keycloak or AIB identity provider**. Because #222 still requires *some* `Authorization` bearer to be present to trigger OPA (the G1 gap in [ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md)), a dummy bearer suffices when JWT authn is off. This mode is **spoofable and non-production**, and must be documented as such.
- **Issuer configured — verified mode.** The gateway JWT authn validates the subject token; the operator injects the IdP JWKS into the policy data (`data.kaos.jwks` alongside `data.kaos.grants`); and the rego uses `io.jwt.decode_verify` on the actor token (**V1**, self-contained in OPA, covering the custom `x-agent-authorization` header that gateway JWT authn does not natively validate; key rotation is an operator ConfigMap refresh). An optional later hardening (**V2**) adds a gateway JWT authn provider for `x-agent-authorization` so the rego can decode-trust; V2 needs dual-provider (subject + actor) verification at the gateway.

The rego ships branching on `data.kaos.jwks` presence (`decode_verify` if present, else `decode`), and the operator injects JWKS only when an issuer is configured. No new subsystem is introduced.

### Token issuance is AIB-only today

Agent credential minting, token issuance, and JWKS are **AIB-only** today: the issuer is the broker, the token endpoint is `<issuer>/oauth2/token`, the JWKS is `<issuer>/oauth2/jwks.json`, and credentials come from AIB admin `/agents/{id}/client-credentials`. Without AIB there is no authenticated agent token. The runtime token client is provider-agnostic, but KAOS automates only the AIB path. An **AIB-less issuer** (Keycloak client-per-agent, or a Kubernetes projected ServiceAccount token as actor identity) is a deferred followup — see [followups](../plan/followups.md); it pairs with the standalone KAOS-run OPA seam in [ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md).

## Consequences

Positive: one logical identity makes the two authorization models interchangeable and grants auditable; verification is cryptographic on the same trust root as the subject token; the demo/verified gradient lets coarse authorization be demonstrated with no identity provider while keeping a real production posture one config flag away. Negative: the default demo mode is spoofable and must be clearly fenced off from production; AIB-less agent-token issuance does not exist yet, so a fully AIB-free deployment cannot authenticate agents until the followup lands; the logical-identity-equals-token-`sub` assumption must be verified against broker behaviour at implementation. Follow-on: [ADR 0003](./adr_0003_authorization-models-and-policy-data.md) consumes these identities as grant keys; the AIB-less issuer and the V2 gateway actor-JWT provider are tracked as followups.

## Alternatives considered

Trust the actor header without verification in production — rejected: spoofable; only acceptable as an explicitly non-production demo mode. Verify the actor token only at the gateway (V2) from day one — deferred: needs dual-provider gateway JWT config; rego `decode_verify` (V1) is self-contained and ships first. Mandatory identity provider always — rejected: blocks the no-dependency demo path the project wants. Random per-deployment identity keys — rejected: not stable or verifiable across redeploys and across the two models.
