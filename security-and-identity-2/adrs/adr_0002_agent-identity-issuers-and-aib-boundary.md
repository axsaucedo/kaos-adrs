# ADR 0002 — Agent identity, issuers, and the AIB boundary

**Status**: Proposed
**Date**: 2026-07-11
**Depends on**: [ADR 0001](./adr_0001_enforcement-topology-pdp-and-policy-delivery.md) (the PDP consumes issuer JWKS and identity mappings via `data.kaos.*`)
**Research**: [002](../research/002-aib-agent-authn-surface.md), [005](../research/005-control-plane-pdp-and-relationship-model.md)

## Amendment (2026-07-12) — AIB is removed as an agent identity issuer

A live end-to-end validation ([manual e2e "Flow E"](../impl/learnings/manual-e2e-phase2-validation.md)) and an [independent assessment of the broker code](../adrs/adr_0004_aib-token-exchange-and-consent.md) falsify this ADR's "AIB as an optional identity issuer" framing. The original text below is retained for history; where it conflicts, this amendment governs.

- **The three agent identity issuers are `serviceaccount` and `oidc` (Keycloak DCR) only. AIB is not an identity issuer.** The "identity-only AIB adapter" (Option 3; Decision 5's "AIB remains selectable as the agent issuer"; the "Keycloak + AIB agent issuer (exchange off)" chart posture) does not exist: the broker rejects agent registration without ≥1 permission set, and a permission set must reference a real third-party service + scope — so registering an agent purely for identity is impossible and meaningless.
- **AIB's only role is token exchange**, specified (and gated on a spike) in [ADR 0004](./adr_0004_aib-token-exchange-and-consent.md). An agent is registered in AIB **iff** it declares a real third-party service. Exchange is an **orthogonal optional capability**, not an `identity.provider` value and not "required when exchange is enabled" — enabling exchange does not make AIB the issuer of any agent's internal actor token (that stays SA or Keycloak-DCR).
- **Consequences for this ADR:** the `identity.provider: serviceaccount | oidc | aib` selector drops `aib`; the AIB adapter is not a retained standalone authn adapter; the chart's AIB-issuer posture is removed. The F0 single-issuer mechanism and the multi-issuer JWKS story still apply to `serviceaccount`/`oidc`.

## Context

With ADR 0001 placing the authorization decision in a KAOS-owned PDP, the identity provider's role shrinks to what IdPs actually do: issue verifiable credentials and tokens. This ADR decides who issues agent (actor) credentials, how workloads obtain and present them, how the gateway and PDP verify them, and — since AIB is no longer an enforcement component — the explicit contract of what KAOS still uses AIB for.

The phase-1 baseline that carries over ([research/002](../research/002-aib-agent-authn-surface.md)): agents present an actor token in `x-agent-authorization`; the gateway `agent` JWT provider verifies it against the issuer's JWKS; the token `sub` maps to the logical identity `kaos://agent/<ns>/<name>`; the runtime token client (`pydantic-ai-server/aib/identity.py`, provider-agnostic, F2 tracks folding it into the SDK) obtains tokens via `client_credentials`. This all worked end to end in phase 1 against AIB — the question is not whether the pattern works but which issuer backs it in which posture, now that AIB is optional.

## Options considered (issuers)

1. **Kubernetes projected ServiceAccount tokens (chosen for the in-cluster posture)** — the kubelet projects an auto-rotated, audience-bound token into the agent pod; the API server is a genuine OIDC issuer (discovery + JWKS). No external issuer, no secrets to mint/rotate/store, no IdP projection at all, and no token-endpoint round-trip in the workload. The `sub` is `system:serviceaccount:<ns>:<sa-name>`, so identity mapping to `kaos://agent/...` moves into projected policy data.
2. **OIDC provider clients via RFC 7591/7592 Dynamic Client Registration (chosen for the OAuth-world posture)** — a provider-generic `OIDCProjector` registers one client per agent through standard DCR and manages it via RFC 7592; Keycloak supports DCR natively. Chosen when agent identity must participate in the broader OAuth ecosystem: agents called from outside the cluster, agents acting as OAuth clients to third parties, multi-cluster trust domains.
3. **AIB `client_credentials` + JWKS, excluding token exchange (retained as an optional adapter)** — the proven phase-1 subset: agent registration (`POST /api/agents`), credential mint/rotate/revoke, LocalClient token minting, public JWKS ([research/002](../research/002-aib-agent-authn-surface.md)). Complete and standalone — none of it touches the exchanger, vault, consent, or ext_proc. Retained because it is the only path to AIB's differentiating capability (consent-based third-party delegation, ADR 0004) and it is already implemented and demonstrated.

These are not competing globally — they are competing *per posture*, and the real decision is the abstraction that makes them interchangeable.

## Decision

1. **Issuers are preset-selectable behind one abstraction.** The gateway `agent` JWT provider, the projection, and the policy see only three things per issuer: an `iss` value, a JWKS, and an identity mapping (token `sub` → `kaos://agent/<ns>/<name>`). Concretely a chart-level `agentIdentity.issuer: serviceaccount | oidc | aib` selection; everything downstream is derived from it. No component outside the issuer adapter may know which issuer is in use.
2. **Posture mapping**: `kaos-internal` uses **ServiceAccount tokens** (zero external dependencies, matching its agent-plane security scope per research/005). Keycloak-backed postures default to **DCR clients against the same Keycloak** (one system serving both planes). **AIB remains selectable** in any posture as the agent issuer — required when ADR 0004's exchange path is enabled, otherwise a preference. The issuer is a *value within* presets, not a multiplier of preset names.
3. **ServiceAccount issuer mechanics**: one dedicated ServiceAccount per agent (created by the operator, as today for workload identity); a projected token volume with a single KAOS-defined audience (e.g. `kaos-gateway`), kubelet-rotated; the runtime token client gains a read-token-from-file provider (no token endpoint involved). JWKS reaches verifiers through the existing projection mechanism: the operator fetches the API server's OIDC discovery/JWKS (it already has cluster credentials) and injects it into `data.kaos.jwks` for the PDP's in-policy verification (ADR 0001); the gateway `jwt_authn` agent provider points at the cluster JWKS where reachable, and where anonymous issuer-discovery is disabled the PDP's in-policy verification remains the authoritative check. Identity mapping (`system:serviceaccount:<ns>:<name>` → `kaos://agent/<ns>/<name>`) is one projected entry per agent — derived, like grants, from the Agent CRD.
4. **IdP projection is credential provisioning only.** For OIDC/AIB issuers the projector's whole job is: ensure a client exists per agent, deliver/rotate its secret as a K8s Secret, delete on agent deletion. The provider-generic `OIDCProjector` (DCR) and the AIB adapter (admin API) are both implementations of the existing `PolicyProjector` seam (`operator/controllers/authz_projection_controller.go`); registering services, binding permission sets, and any grant or policy state are **out of the IdP** permanently. Under the ServiceAccount issuer, IdP projection disappears entirely.
5. **The AIB boundary**: AIB is an **optional issuer adapter, never a required component and never an enforcement component**. Its base surface in KAOS is exactly the research/002 authn subset. **Permission sets are exchange-scoped**: the adapter binds them only when the ADR 0004 feature is enabled, and they never influence the PDP path. The cancelled upstream-contribution track stays cancelled; the fork is not a dependency (its access-check *model* is reused in ADR 0003, its code is not).
6. **Re-entry criteria for deeper AIB integration** (verbatim from the phase-1 close-out, now owned by ADR 0004's assessment): (a) AIB ships an authorization surface decoupled from token exchange, or (b) KAOS adopts consent-based third-party delegation and AIB's consent/vault UX is the best implementation.
7. **Issuer/`iss` consistency (F0) is solved by construction**: a single chart value (the externally visible issuer URL) feeds both the issuer's own configuration (e.g. AIB `server.enduser.public_url`) and every verifier (gateway provider `issuer`, projected JWKS entry). No component states the issuer independently, so the phase-1 `Jwt_issuer_is_not_configured` class of mismatch cannot be rendered. A startup check in the projection (mint or fetch a token/discovery document and compare `iss`) surfaces residual misconfiguration as a status condition rather than as request-time 401s.
8. **Verification placement follows ADR 0001**: `jwt_authn` in front for authn-layer 401s, in-policy verification in the PDP as the authoritative check. Multi-issuer setups (e.g. Keycloak users + SA agents, or Keycloak users + AIB agents) are the normal case: `data.kaos.jwks` is keyed by issuer, and the rego selects by the token's `iss` — the phase-1 mechanism, now with more issuers.

## Consequences

- **`kaos-internal` loses its last external dependency**: agent identity comes from the cluster itself, auto-rotated, with no Secrets to manage — completing its graduation to the agent-plane security posture (research/005). Cost: SA-issued identity is meaningless outside the cluster's trust domain; postures needing OAuth-world identity must choose an OIDC issuer.
- **A new runtime code path**: the token client needs the file-based provider for projected tokens (extends F2's SDK consolidation). Small, and removes the client-credentials secret handling in that posture.
- **A new operator component**: the `OIDCProjector` (DCR). Bounded scope — three lifecycle operations against a standard protocol — and it replaces, rather than adds to, the larger phase-1 ambition of projecting authorization state into IdPs.
- **The AIB adapter shrinks**: permission-set binding moves behind the ADR 0004 feature flag; the projection's AIB calls in the default configuration reduce to agent registration and credential lifecycle. Chart-wise, AIB (and its ext_proc sidecar) is simply not installed unless selected.
- **Keycloak DCR needs bootstrap configuration**: an initial access token or trusted-service-account setup for client registration, provisioned by the KAOS chart in Keycloak-backed presets. This is standard Keycloak administration but is new chart surface.
- **JWKS freshness becomes a projection concern for all issuers** (accepted in ADR 0001): key rotation at the issuer must reach `data.kaos.jwks` within the delivery bound (~90s ConfigMap propagation). Issuers rotate keys with overlap windows far exceeding this; documented, not mitigated.
- **What is deleted from phase 1**: mandatory AIB in any preset, permission-set binding on the default path, and the notion of the IdP as a policy store.

## Appendix — chart surface per configuration variation

The existing `security.agentAuth` / `security.userAuth` blocks evolve rather than being replaced. Structural deltas from the phase-1 chart: a new `security.pdp` block (the chart deploys the PDP itself, so `extAuthzUrl` gains a default of the chart's own PDP Service and becomes an override for swapping backends per ADR 0001's contract); a new `agentAuth.identity.provider` selector implementing this ADR's issuer abstraction, with issuer-specific settings nested under it so exactly one issuer block is active; `extProcUrl` moves from top-level enforcement config into the ADR 0004 `tokenExchange` gate; and **`authorization.provider` is deleted** — its `aib` value is gone as an enforcement mode and `none` collapses into `pdp.enabled: false`, leaving a knob with one setting (`kaos`), which should not be a knob. `policyDataSource` (automated/manual) and `policyRegoOverride` survive as genuine modes of the one remaining compilation pipeline. `pdp.failOpen` deliberately does not exist as a key: fail-closed is hardcoded, since a misconfigured fail-open silently voids all authorization — strictly worse than any quarantined demo flag.

Common to every variation (ADR 0001 core — PDP always on, fail-closed):

```yaml
security:
  pdp:
    enabled: true               # the authorization switch: deploys stock OPA (2 replicas + PDB)
                                # and the ext_authz SecurityPolicy; extAuthzUrl defaults to
                                # kaos-pdp.<release-ns>.svc:9191, set only to swap backends
  agentAuth:
    authorization:
      policyDataSource: automated   # manual / policyRegoOverride carry over unchanged
    projection:
      policyConfigMap: {name: kaos-authz, namespace: kaos-system}   # mounted by the PDP
```

`kaos-internal` — ServiceAccount issuer, zero external systems (OPA image pull aside, the cluster itself is the only dependency — the API server is the token issuer):

```yaml
security:
  agentAuth:
    identity:
      provider: serviceaccount  # projected SA tokens, audience kaos-gateway; no IdP projection exists
  userAuth: {}                  # no user plane; AccessGrants → Enforced=False
```

Keycloak users + DCR agent clients — one external system serving both planes:

```yaml
security:
  agentAuth:
    identity:
      provider: oidc            # generic RFC 7591/7592 OIDCProjector
      oidc:
        issuer: http://keycloak.kaos-system.svc:8080/realms/kaos
        registration:
          initialAccessTokenSecretRef: {name: kaos-dcr-bootstrap, key: token}
    credentialSecretPrefix: kaos-agent
  userAuth:
    issuer: http://keycloak.kaos-system.svc:8080/realms/kaos
    audience: kaos
```

Keycloak users + AIB agent issuer (exchange off — the proven phase-1 authn subset; external systems: Keycloak + AIB):

```yaml
security:
  agentAuth:
    identity:
      provider: aib
      aib:
        issuer: http://aib-enduser.aib-system.svc:8000    # single value feeds broker public_url AND all verifiers (F0 by construction)
        adminUrl: http://aib-broker.aib-system.svc:8000/api
    credentialSecretPrefix: kaos-aib
  userAuth:
    issuer: http://keycloak.kaos-system.svc:8080/realms/kaos
    audience: kaos
```

The above + ADR 0004 token exchange — the only configuration where ext_proc and permission sets return (adds the third-party IdPs the feature exists to reach):

```yaml
security:
  agentAuth:
    identity:
      provider: aib
      aib: {issuer: ..., adminUrl: ...}
    tokenExchange:              # the ADR 0004 feature gate
      enabled: true
      extProcUrl: aib-ext-proc.aib-system.svc:50051   # applied ONLY to third-party egress routes
      bindPermissionSets: true                        # exchange-scoped, never in the PDP path
  userAuth: {issuer: ..., audience: kaos}
```

Quarantined demo flags remain explicit and are never implied by a preset (e.g. `agentAuth.authorization.agentJwtVerification: skip`).
