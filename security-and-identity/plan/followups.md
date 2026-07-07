# Followups — deferred out of the critical path

These are explicitly out of scope for the current authorization work (phases **P13–P15** in [proposed-split](./proposed-split.md), realising the fresh [ADR set](../adrs/adr_high_level_components.md)). They are recorded so they are not lost. The list also absorbs the previously-planned-but-unimplemented old P13 (docs) and old P14 (upstream) phases whose numbers P13/P14 have been reused; the old P15 (strict gateway) is reinstated as the current phase P15.

## F1 — AIB-less agent-identity issuer

Today, agent authentication (credential minting, token issuance, JWKS) is **AIB-only**: the issuer is the broker, the token endpoint is `<issuer>/oauth2/token`, the JWKS is `<issuer>/oauth2/jwks.json`, and credentials come from AIB admin `/agents/{id}/client-credentials`. Without AIB there is no authenticated agent token, so a fully AIB-free deployment cannot authenticate agents even though [ADR 0003](../adrs/adr_0003_authorization-models-and-policy-data.md) Model 1 is otherwise broker-independent. The runtime token client (`pydantic-ai-server/aib/identity.py`) is provider-agnostic (any token endpoint plus client id/secret), but KAOS automates only the AIB path.

Explore and **pick one**:

- **Keycloak client-per-agent.** Reuse the user IdP as the trust anchor; needs a "keycloak sync" analogous to the AIB credential mint (create a client per agent, expose its issuer/JWKS to the rego verification path in [ADR 0002](../adrs/adr_0002_identity-and-authentication.md)).
- **Kubernetes projected ServiceAccount token as actor identity.** Most Kubernetes-native, AIB- and Keycloak-free; the SA identity is not `kaos://agent/...`, so the logical identity must be mapped in the OPA data; audience and rotation specifics need design.

This pairs with the **standalone KAOS-run OPA** seam kept in [ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md): together they enable coarse enforcement with no AIB deployed (identity issuer + KAOS-run OPA behind the optional ext_authz seam).

## F2 — Python SDK consolidation

The AIB Python SDK is no longer a separate upstream contribution (AIB PR #399 is abandoned). The runtime token client is already vendored in KAOS at `pydantic-ai-server/aib/`. This followup **folds that vendored client into the main KAOS Python SDK** and simplifies the surface — there is no separate SDK to maintain or upstream. Scope: relocate/rename the module into the SDK package, remove the "temporary home / to-be-upstreamed" framing from docs and ADRs, and keep the provider-agnostic token client as a first-class SDK capability (which F1 also builds on).

## F3 — Autonomous-mode enforcement (G1 gap)

[ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md) records that OPA only runs when a subject bearer is present (#222), so purely autonomous agent actions with no user token bypass authorization. Closing this needs either an AIB change (run OPA on actor-only requests) or treating the actor token as the bearer in autonomous flows. Deferred; user-present flows always enforce in P13–P14.

## F4 — ConfigMap-as-local-bundle hot-reload

[ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md) starts Model-1 data delivery on `policy.path` (static, restart-on-change). Graduating to `policy.config_file` local-bundle hot-reload avoids the ext_proc restart on data changes but is **unverified against #222** and needs a spike. Deferred; the rego stays static either way.

## F5 — V2 gateway JWT provider for the actor token

[ADR 0002](../adrs/adr_0002_identity-and-authentication.md) ships actor-token verification as rego `io.jwt.decode_verify` against an injected JWKS (V1). A later hardening (V2) validates `x-agent-authorization` at the gateway via an Envoy Gateway JWT authn provider so the rego can decode-trust; this needs dual-provider (subject + actor) gateway verification. Deferred.

## F6 — Strict gateway-only traffic, decoupled from authorization (reinstated as phase P15)

**Reinstated as active phase P15** — no longer a followup. It sits at the top of the P13 → P14 → P15 stacked series and builds directly on the P13 security-config decoupling that separates the "security enabled" predicate from `ExtAuthzURL`. See [`proposed-split.md`](./proposed-split.md) (P15) and the detailed plan [`P15-strict-gatewayapi-decoupling.md`](./P15-strict-gatewayapi-decoupling.md).

Summary retained for context: make network-level bypass prevention (deny direct workload-to-workload ClusterIP, force traffic through the Envoy Gateway) available **independently** of the authorization stack, exposed as a single positively-named `security.strictGatewayApi.enabled` switch (env `SECURITY_STRICT_GATEWAY_API_ENABLED`), replacing the inverse escape hatch. Strict traffic requires recreating the KIND cluster with a NetworkPolicy-enforcing CNI (Calico), since the default kindnet does not enforce NetworkPolicy.

## F7 — Cross-component documentation pass (was P13)

A dedicated pass bringing all user- and operator-facing docs up to the same structure as the implementation (security/identity model, install flow, CRD surface, SDK, folded projection controller, authorization modes). P14 already ships per-mode docs and examples for the authorization work; this followup is the broader consistency sweep across every component, done once the surface settles.

## Cancelled — Upstream contribution of the AIB-side work (was P14)

The original plan contributed the AIB-side work (deployability foundation, access-check API, Python SDK) upstream from a fork. This is **cancelled**. AIB `main` already embeds OPA in ext_proc (#222), the standalone access-check service (#398) and separate SDK (#399) are abandoned, and the runtime token client folds into the KAOS Python SDK ([F2](#f2--python-sdk-consolidation)). The only remaining AIB dependency is `main`+#222 plus PR #397 (deployability), which is maintained on the fork without an upstream-contribution track.
