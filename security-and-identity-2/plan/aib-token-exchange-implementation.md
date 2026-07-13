# Implementation plan — AIB delegated third-party access (token exchange)

**Status**: Implemented and manually verified on the wire (2026-07-13)
**Realises**: [ADR 0004](../adrs/adr_0004_aib-token-exchange-and-consent.md) "The design (spike-validated)"
**Outcome**: E0-E6 shipped on `feat/kaos-token-exchange` and passed against a mock GitHub-style OAuth provider/API. See [the manual evaluation learnings](../impl/learnings/aib-token-exchange-manual-eval.md). Real GitHub validation, ServiceAccount-primary exchange credentials, and stronger actor-to-delegated-`azp` cross-checking remain follow-ups.

## Design in one paragraph (from the spike)

An exchange-enabled agent, on a **third-party egress route only**, gets the requesting user's Keycloak token **re-minted in the runtime** into a token carrying `azp = the agent` and `sub = the user` (a standard Keycloak internal token-exchange call using the agent's own DCR client), which AIB's **ext_proc** (its own self-managed release) exchanges via RFC 8693 for the user's real third-party token from AIB's vault, swapping it onto the outbound request. Consent + vault seeding happen once via a user-completed OAuth authorization-code flow surfaced as a fail-with-URL. The KAOS operator's only job is a thin seam: attach ext_proc to the declared egress routes and project the third-party services + agent→service permission sets into AIB. AIB is never an identity issuer and never touches internal traffic; the PDP path has no dependency on it.

## Guiding constraints (non-negotiable)

- **AIB is self-managed like Keycloak** — the operator deploys none of it. AIB's chart must ship ext_proc (upstream fix).
- **ext_proc attaches to declared third-party egress routes ONLY** — never internal; its token-swap must be structurally unable to leak onto internal paths (ADR 0001).
- **AIB is exchange-only** — never an identity issuer; permission sets are always real (never dummy); identity stays `serviceaccount`/`oidc`.
- **Feature-gated, off by default; static per-MCP credentials remain the default.**
- **Validate on a live cluster with a mock OAuth provider** before trusting it — the spike harness under `tmp/aib-spike/` is the starting point. No code-only verification.

## Completed phases

### Phase E0 — Prerequisites — complete
- Confirm/land the **AIB chart shipping ext_proc** (upstream to `aib-222-verify` or a KAOS-pinned values/overlay that deploys it). Without a deployable ext_proc there is no in-band path.
- Confirm the concrete use case + the mock third-party OAuth provider + dummy API (reuse `tmp/aib-spike/mock`).
- **Gate**: do not proceed to E1 until ext_proc is deployable and a use case is committed.

### Phase E1 — Declaration surface + AIB projection (operator, thin seam #2) — complete
- Add the declaration: which agent may reach which third-party service + scopes (a spec field on Agent, or a small `ThirdPartyService` + binding CRD — pick per ADR 0004's "declaration surface"). Namespaced, GitOps-reviewable.
- Re-introduce **exchange-scoped** projection into AIB: register the third-party **service** and the agent→service **permission set** (always real). This is behind the exchange feature gate; it does NOT touch the PDP path or `data.kaos.*`.
- Register the exchange-enabled agent in AIB (now valid — it has a real permission set).
- Tests: projection produces the AIB service + permission set for a declared binding; nothing projected when the feature is off.

### Phase E2 — Runtime re-mint (`kaos_identity`) — complete for Keycloak-DCR Agents
- On a third-party egress call, the runtime re-mints the user subject token via Keycloak's token endpoint (token-exchange grant), authenticated as the agent's own DCR client → token with `azp=agent`, `sub=user`, `aud=token-exchange-broker`.
- Only on declared third-party routes; internal calls unchanged (propagate as today).
- SA-primary agents: use the provisioned secondary Keycloak exchange client (documented); if absent, fail clearly.
- Tests: re-mint produces the correct claims; internal path untouched; no-Keycloak-client case errors cleanly.

### Phase E3 — Gateway ext_proc attachment (operator, thin seam #1) — complete
- Operator generates an `EnvoyExtensionPolicy` attaching AIB's ext_proc to the declared third-party egress routes ONLY. Ordering: after `jwt_authn` and the ext_authz PDP. Header ownership airtight; provably never on internal routes.
- The deny-with-authorization-URL round-trips from ext_proc back to the caller (header vs body — pin from the spike).
- Tests: policy generated only for declared egress routes; internal routes never carry it; a CI/unit invariant that ext_proc is never attached to an internal route.

### Phase E4 — Consent flow (fail → approve → retry) — complete
- Wire the fail-with-URL: an exchange without consent/vault returns the authorization URL; the user completes the OAuth authorization-code flow (seeds vault + consent); retry succeeds. Expiry/revocation surface the same way.
- KAOS UI wrapping deferred; the raw flow is the contract.
- Tests: no-consent → URL returned; after mock OAuth completion → 200; vault-session delete → re-deny.

### Phase E5 — Live end-to-end validation — complete as a manual evaluation
- Promote the spike (`tmp/aib-spike/`) into a repeatable KIND validation: fresh cluster, Keycloak, AIB (with ext_proc), mock OAuth + dummy API, a declared exchange-enabled agent. Prove on the wire: re-mint → ext_proc exchange → third-party token → dummy API 200; plus all deny paths (absent agent, no consent, no vault, wrong audience, caller-binding mismatch) and revocation.
- Never touch other clusters. Capture evidence. Because it needs Calico? No — exchange doesn't need NetworkPolicy; standard KIND is fine.
- Decide whether this becomes a gated CI job (heavy — Keycloak + AIB) or a documented manual/opt-in validation (mirror the manual-e2e decision; likely opt-in, not in the core matrix).

### Phase E6 — Docs — complete
- A `docs/examples/`-style hands-on example (like `authorization.md`) for the exchange flow, with the executed part minimal and the heavy Keycloak/AIB/consent parts as `.noeval` (per the long-running-test caution). Update the security docs to describe AIB-as-exchange-only.

## Decisions made

- Declaration surface — **REVISED 2026-07-13** (see ADR 0004): the `ThirdPartyService` CRD (first implementation, validated live) is superseded by an **AIB-native** surface. The operator registers Agents into AIB by stable logical name (`kaos/<ns>/<name>`, keeping the DCR `client_id` current) and REFLECTS AIB's admin-configured services/permission sets into: generated egress `Backend`/`HTTPRoute` objects, ext_proc attachment on exactly those generated routes, and per-agent re-mint targets. One admin surface (AIB), no third-party YAML, no CRD. E2/E4 runtime work is unchanged by this rework.
- ext_proc attachment: one operator-generated `EnvoyExtensionPolicy` per declared third-party route; internal routes are never selected implicitly.
- Current identity restriction: exchange requires Keycloak user and Agent identity. ServiceAccount-primary exchange credentials remain deferred.
- Validation: manual/opt-in rather than part of the core CI matrix; the completed rig used a mock provider and captured wire evidence.

## Remaining follow-ups

- Validate a real provider such as GitHub, including production scopes, refresh, and provider-side revocation.
- Decide and implement the secondary Keycloak credential model for ServiceAccount-primary Agents, or keep the Keycloak-DCR restriction explicit.
- Harden caller binding by cross-checking the delegated subject `azp` against the verified actor identity at the PDP/AIB boundary.
- Persist Keycloak and AIB state in repeatable environments and declaratively manage Keycloak 26's per-client exchange permission and target audience mapper.
