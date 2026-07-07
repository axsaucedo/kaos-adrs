# Followups — deferred out of the initial cut

These are explicitly out of scope for the initial KAOS↔AIB authorization implementation (see [proposed-split](./proposed-split.md) and the [ADR set](../adrs/adr_high_level_components.md)). They are recorded so they are not lost.

## F1 — AIB-less agent-identity issuer

Today, agent authentication (credential minting, token issuance, JWKS) is **AIB-only**: the issuer is the broker, the token endpoint is `<issuer>/oauth2/token`, the JWKS is `<issuer>/oauth2/jwks.json`, and credentials come from AIB admin `/agents/{id}/client-credentials`. Without AIB there is no authenticated agent token, so a fully AIB-free deployment cannot authenticate agents even though [ADR 0003](../adrs/adr_0003_authorization-models-and-policy-data.md) Model 1 is otherwise broker-independent. The runtime token client (`pydantic-ai-server/aib/identity.py`) is provider-agnostic (any token endpoint plus client id/secret), but KAOS automates only the AIB path.

Explore and **pick one**:

- **Keycloak client-per-agent.** Reuse the user IdP as the trust anchor; needs a "keycloak sync" analogous to the AIB credential mint (create a client per agent, expose its issuer/JWKS to the rego verification path in [ADR 0002](../adrs/adr_0002_identity-and-authentication.md)).
- **Kubernetes projected ServiceAccount token as actor identity.** Most Kubernetes-native, AIB- and Keycloak-free; the SA identity is not `kaos://agent/...`, so the logical identity must be mapped in the OPA data; audience and rotation specifics need design.

This pairs with the **standalone KAOS-run OPA** seam kept in [ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md): together they enable coarse enforcement with no AIB deployed (identity issuer + KAOS-run OPA behind the optional ext_authz seam).

## F2 — Python SDK consolidation

The AIB Python SDK is no longer a separate upstream contribution (AIB PR #399 is abandoned). The runtime token client is already vendored in KAOS at `pydantic-ai-server/aib/`. This followup **folds that vendored client into the main KAOS Python SDK** and simplifies the surface — there is no separate SDK to maintain or upstream. Scope: relocate/rename the module into the SDK package, remove the "temporary home / to-be-upstreamed" framing from docs and ADRs, and keep the provider-agnostic token client as a first-class SDK capability (which F1 also builds on).

## F3 — Autonomous-mode enforcement (G1 gap)

[ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md) records that OPA only runs when a subject bearer is present (#222), so purely autonomous agent actions with no user token bypass authorization. Closing this needs either an AIB change (run OPA on actor-only requests) or treating the actor token as the bearer in autonomous flows. Deferred; user-present flows always enforce in the initial cut.

## F4 — ConfigMap-as-local-bundle hot-reload

[ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md) starts Model-1 data delivery on `policy.path` (static, restart-on-change). Graduating to `policy.config_file` local-bundle hot-reload avoids the ext_proc restart on data changes but is **unverified against #222** and needs a spike. Deferred; the rego stays static either way.

## F5 — V2 gateway JWT provider for the actor token

[ADR 0002](../adrs/adr_0002_identity-and-authentication.md) ships actor-token verification as rego `io.jwt.decode_verify` against an injected JWKS (V1). A later hardening (V2) validates `x-agent-authorization` at the gateway via an Envoy Gateway JWT authn provider so the rego can decode-trust; this needs dual-provider (subject + actor) gateway verification. Deferred.
