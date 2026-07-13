# ADR 0004 — AIB token exchange and the consent flow (F9)

**Status**: Proposed
**Date**: 2026-07-11
**Depends on**: [ADR 0001](./adr_0001_enforcement-topology-pdp-and-policy-delivery.md) (filter composition rules), [ADR 0002](./adr_0002_agent-identity-issuers-and-aib-boundary.md) (the AIB adapter and re-entry criteria)
**Research**: [001](../research/001-why-aib-cannot-authorize-internal-traffic.md), [002](../research/002-aib-agent-authn-surface.md), [005](../research/005-control-plane-pdp-and-relationship-model.md)

## Amendment (2026-07-12) — AIB is exchange-only; identity is never AIB

This ADR was written before P18/P19 shipped and before a live end-to-end validation. Findings from [manual e2e "Flow E"](../impl/learnings/manual-e2e-phase2-validation.md), an [independent code assessment](../impl/learnings/aib-exchange-boundary-assessment.md), and a **live in-cluster spike (2026-07-12) that PASSED** ([SPIKE-RESULT](#the-design-spike-validated-2026-07-12)) require correcting its central premise. The original sections below are retained for history; where they conflict, this amendment and the **spike-validated design** section govern.

**Corrections (proven from the broker code / live cluster):**

1. **AIB is not an agent identity issuer.** P19's ServiceAccount and Keycloak-DCR issuers own agent identity completely. An "identity-only AIB" posture is **falsified**: the broker rejects agent registration without ≥1 permission set, and a permission set must reference a *real* third-party service and scope (`permission_set.go:18-49`). So AIB is used **only for token exchange**, and an agent is registered in AIB **iff** it declares a real third-party service (always a real permission set — never a dummy).

2. **The exchange uses two independent tokens, not the agent's actor token.** RFC 8693 to AIB carries `subject_token` (the user's Keycloak token) plus a separate `client_assertion` (an OAuth `client_credentials` JWT for the caller). The exchange does **not** authenticate the caller from `x-agent-authorization`. So an exchange-enabled agent holds a *distinct* AIB exchange credential in addition to its Keycloak/SA identity — these serve different purposes.

3. **Keycloak subject-token trust is supported but constrained.** AIB validates a subject token against the configured upstream issuer + a required exchange audience (default `token-exchange-broker`) — so Keycloak *can* be the subject issuer, provided the token is minted with the exact issuer and audience.

4. **The central open risk (the spike's go/no-go): AIB derives the acting agent from the *subject* token's `azp` (or a configured claim).** A KAOS-propagated Keycloak user token carries `azp` = the user-facing client, **not** the acting agent — so it can pass validation yet resolve the wrong agent or none. Making option (b) real requires one of: mint an agent-specific subject token per hop (`azp` = agent), a trusted custom claim carrying the AIB agent id, or an upstream AIB change binding the agent to the client assertion. AIB's default caller CEL is literally `true` — insufficient for multi-agent; a real caller↔agent binding is required.

5. **SA-primary agents cannot present their K8s token as the exchange assertion** (assertion trust is tied to the configured upstream issuer); they need a secondary Keycloak/upstream exchange credential.

6. **Keycloak-native exchange is green-field, not a drop-in.** Our deployed Keycloak is **26.0**; standard token exchange arrived in 26.2 and external-IdP exchange remains preview/legacy. Keycloak 26.6/26.7 add JWT-grant + Identity-Brokering-V2 as supported primitives, but none supplies AIB's per-(user, agent, service) consent triple or a gateway filter. It is a separate build to compare by prototype, not configuration.

**Decision:** adopt **AIB exchange-only** (option b), keep static per-MCP credentials as the default, gate the feature, and require a concrete third-party use case before implementation. The spike passed; the settled design follows.

## The design (spike-validated, 2026-07-12)

The live in-cluster spike (fresh KIND cluster, real Keycloak + AIB + a mock third-party OAuth provider and API) proved the exchange works and pinned every mechanic. Verdict: **yes, with a re-mint requirement.** Evidence: correct exchange → third-party token → mock API accepts (200); all deny paths deny (absent-agent, no-consent, no-vault, wrong-audience, caller-binding-mismatch); revocation (delete vault session) re-denies.

### The two-exchange chain

Delegated third-party access is a *three-party* statement — "user Alice, via agent Researcher, may act on GitHub" — but a propagated Keycloak user token only encodes two (Alice + the login client, `azp = login-client`). AIB identifies the acting agent from `subject_token.azp`, so the propagated token resolves the wrong agent. The design therefore chains two standard exchanges:

```
① Alice's login token (sub=alice, azp=login-client)
      ── Keycloak internal token-exchange, authenticated AS the agent's own client ──►
② Re-minted token (sub=alice, azp=agent-researcher, aud=token-exchange-broker)
      ── AIB RFC 8693 exchange (② + the agent's client-assertion) ──►
③ GitHub access token (Alice's real credential, from AIB's vault)
      ──► agent calls api.github.com as Alice
```

Both ① and ② are calls to **standard endpoints** — Keycloak's token endpoint and AIB's exchange endpoint. No custom endpoint, no rego (this is token *acquisition*, not an authorization decision; the PDP is not in this path).

### Spike-proven mechanics (do not re-derive)

- AIB resolves the agent via `agent_id_expression: resolveAgentIdByClientId(subject_token.azp)`.
- Caller↔agent binding via CEL `client_assertion.azp == subject_token.azp` (AIB's default caller CEL is `true` — insufficient; this binding is required).
- Required audience `token-exchange-broker`; subject token issuer = Keycloak (trusted as the configured upstream).
- Consent (`UserGrant`) + a vault session are created **only** by a completed interactive OAuth authorization-code flow against the third party (the only vault write path); revocation = delete the vault session.

### Component boundaries — thin seam (AIB self-managed like Keycloak)

- **AIB (broker + ext_proc + vault) = its own self-managed Helm release**, exactly like Keycloak. The KAOS operator deploys **none** of it. (Upstream gap: AIB's chart must actually ship the ext_proc workload — the manual e2e found it does not; this is an AIB-chart fix, not a KAOS workaround.)
- **Runtime (`kaos_identity`) does the re-mint (①)** — a standard Keycloak token-exchange call authenticated as the agent's own Keycloak DCR client. This lives in the runtime because the agent already holds those credentials; putting it at the gateway would require distributing per-agent Keycloak secrets to the gateway.
- **Operator provides a thin integration seam, identical in kind to the Keycloak seam** (JWT-provider config + DCR projection). Decided 2026-07-13 (superseding the earlier "declared egress routes + projection" phrasing, which was ambiguous about where third-party access is administered): the seam is (a) **identity registration** — the operator writes each Agent into AIB as an agent record keyed by its stable logical name (`kaos/<namespace>/<name>`), keeping the record's `client_id` (the Keycloak DCR UUID) current across re-registrations; and (b) **reflection** — the operator reads AIB's services + permission sets (poll-based) and materializes the cluster plumbing they imply: generated egress `Backend`/`HTTPRoute` objects for each service's hostnames, an `EnvoyExtensionPolicy` attaching AIB's ext_proc to **exactly those operator-generated egress routes** (safe-by-construction per ADR 0001 — the operator never attaches ext_proc to a route it did not generate for a third-party service, so the token-swap can never leak onto internal paths), and per-agent `KAOS_TOKEN_EXCHANGE_CONFIG` re-mint targets injected into bound agents only.

### The declaration surface (decided 2026-07-13: AIB-native, no CRD)

"Agent Researcher may reach third-party service GitHub" is administered **in AIB itself**, not in a KAOS CRD. Options weighed: (1) a dedicated `ThirdPartyService` + binding CRD projected one-way into AIB (the P20 first implementation — worked live, but a dual-role resource+grant object, a new public API surface, and hand-authored egress routes made for a poor admin experience for value that was hard to justify); (2) a spec field on the Agent (duplicates service facts per agent); (3) **AIB-native (chosen)** — the admin links the agent's stable logical name (`kaos/<ns>/<name>`, maintained by the operator, never the DCR UUID) to third-party services + scopes using AIB's own service/permission-set model, and KAOS **reflects** that into generated egress routes, ext_proc attachment, and runtime re-mint targets. One config surface (AIB), zero third-party YAML, no CRD to version/support; the platform plane (agents, MCP/model resources, AccessGrants) remains fully CRD/GitOps-based and AIB-free.

Accepted residual costs (explicit): AIB becomes a config authority whose data materializes cluster egress objects (same shape of trust already extended to Keycloak for users; hardenable with an operator-side hostname allowlist); reflection is poll-based (no watch API; fail-static when AIB is unreachable); misconfiguration surfaces as operator events / runtime 403s rather than CRD status (mitigable via Agent status conditions); Git no longer audits third-party access — AIB's records do.

### Consent UX (inherited)

Fail → approve → retry, no async machinery: the ext_proc exchange fails with an authorization URL; the user completes the third-party OAuth flow (seeding the vault + consent); the retry succeeds. Expiry/revocation surface through the same fail-with-URL path. The KAOS UI wrapping is deferred.

### Dependencies and constraints

- Exchange requires the agent to have a **Keycloak client** for the re-mint — so an exchange-enabled agent uses the `oidc` identity issuer, or is provisioned a dedicated Keycloak exchange client. **ServiceAccount-primary agents cannot re-mint** (no Keycloak client) and need a secondary Keycloak exchange credential — documented, decided per deployment.
- Feature-gated; static per-MCP credentials remain the default; **implementation requires a concrete third-party use case** (validated against a mock OAuth provider, as the spike did).

## Context

Everything in ADRs 0001–0003 works with agents acting **as themselves** against internal resources. What none of it provides: an agent calling an *external* OAuth-protected API (GitHub, Google Drive, Slack) **as the requesting user** — delegated third-party access. Note this is distinct from ADR 0003's subject propagation: the user's Keycloak token reaches every internal hop, but it is worthless at api.github.com — GitHub does not trust Keycloak. Per-user third-party access requires the user's *GitHub* credential, which requires consent, a token vault, and RFC 8693 exchange.

This capability was deferred throughout phase 1 and phase 2 as "F9". This ADR exists to turn that deferral into an explicit decision: design the integration end to end, price its complexity honestly, and decide adopt / defer-with-triggers / reject.

**Anchor use case**: an agent operating on GitHub (open PRs, read private repos) with the requesting user's own GitHub identity and permissions — per-user access control and audit on GitHub's side, instead of a shared bot credential.

## The design

### The flow (fail → approve → retry)

The consent UX decision was already made in the first iteration and is inherited here: **consent is an expected failure with a URL, followed by a retry** — no asynchronous approval machinery.

1. Agent calls the GitHub MCP; the ext_proc exchange filter on that egress route attempts the exchange and fails — no consent and/or no vault session for this (user, agent, service).
2. The failure returns to the caller carrying an authorization URL.
3. The user visits the URL and completes a real OAuth authorization-code flow against the third party — the only write path into AIB's vault ([research/001](../research/001-why-aib-cannot-authorize-internal-traffic.md)). AIB stores the access + refresh tokens as a vault session and records the consent (`UserGrant` for the user + agent + service triple).
4. The caller retries; the exchange now finds consent and a live session, swaps the subject token for the vaulted third-party token, and the request proceeds with the user's GitHub identity.
5. Subsequent requests need no re-consent: the vault holds the refresh token and renews access tokens transparently. When the refresh token dies or the user revokes (on either side), the *same* failure-plus-URL surfaces — expiry and first-contact are one failure mode, one recovery path.

The **KAOS UI workflow** wrapping this loop (surfacing the URL, guiding the retry, managing standing connections) is **deferred** — the raw flow is the contract; API callers handle the failure manually until the UI lands. One implementation detail to pin in the spike: how the authorization URL travels from ext_proc's deny back through Envoy to the caller (header vs body).

### Filter composition (from ADR 0001)

AIB's ext_proc returns as an **additional** filter, scoped strictly to third-party egress routes via operator-generated `EnvoyExtensionPolicy`, ordered after `jwt_authn` and the ext_authz PDP. Hard rules: it never attaches to internal routes; its `Authorization` rewrite (vaulted third-party token) must be provably unable to leak onto internal paths; and its absence or failure never weakens internal authorization — the PDP path has no dependency on it.

### Projection scope

The exchange requires a registered service matching the target, a permission set binding the agent to it, a UserGrant, and a vault session. The operator projects **only the first two, only for declared third-party egress targets** — a handful of services, not the phase-1 ambition of mirroring every internal resource into the broker. UserGrants and vault sessions are created exclusively by the user's approval flow and are never projected. This is the `tokenExchange.bindPermissionSets` gate in ADR 0002's chart appendix; permission sets remain exchange-scoped and never touch the PDP path.

### Why AIB and not Keycloak (assessed 2026-07)

Keycloak's supported RFC 8693 exchange (since 26.2) is **internal-to-internal only** — swapping one Keycloak token for another Keycloak token. Its third-party stories are identity-brokering "stored tokens" (requires the user to log in *via* the third party, scopes fixed at IdP configuration) and the legacy external exchange, which is preview and slated for deprecation in favor of RFC 7523 identity chaining (itself preview as of 26.5). Neither has a per-(user, agent, service) consent concept, and neither ships a gateway filter. AIB models exactly our triple (UserGrant per user+agent+service, per-service vault sessions with service-specific scopes, the ext_proc filter). Conclusion: **for delegated third-party access, AIB is the implementation; Keycloak is not a substitute today.** Keycloak identity-chaining maturity is a named re-check trigger. (Sources: [Keycloak 26.2 standard token exchange](https://www.keycloak.org/2025/05/standard-token-exchange-kc-26-2), [token exchange docs](https://www.keycloak.org/securing-apps/token-exchange), [26.5 JWT authorization grant](https://www.keycloak.org/2026/01/jwt-authorization-grant).)

### Simpler alternatives (and why they don't replace this)

1. **Static per-MCP credentials** (PAT/bot token in a Secret) — today's answer; zero new components; one shared identity, no per-user permissions or audit. **Remains the documented default**; the exchange feature is only for use cases that genuinely need the user's own identity downstream.
2. **GitHub App installation tokens** — better scoping, still a bot identity, provider-specific.
3. **Per-MCP self-managed OAuth** — relocates the vault into every MCP server, N times, with no shared consent model. Worse, not simpler.

There is no lighter architecture for per-user third-party identity; the honest simplification is staying on option 1 until a use case forces the move.

## Complexity assessment

- **AIB is operated as a third-party dependency** — deployed from its upstream chart and pointed at, like Keycloak; KAOS owns no broker code, images, or CVEs. Operationally this is moderate-to-low (a chart plus its vault database — the one new stateful component). The real cost is **dependency maturity**: unlike Keycloak, AIB is young with no community backstop, so gaps (F0 chart env/`public_url` injection) resolve on upstream's timeline or via KAOS-side workarounds.
- **The main engineering overhead is composition correctness**, not runtime cost: `EnvoyExtensionPolicy` generation on exactly the egress routes, airtight header ownership, and the deny-payload round-trip. Runtime impact is one exchange/vault hop on third-party egress routes only; internal traffic is untouched.
- **What the fail-and-retry UX decision avoids**: CIBA-style async approval, notification infrastructure, suspended-task state, and KAOS-built consent screens — where "high" complexity would have lived.

## Decision

**Adopt as a gated optional feature — not defer, not reject** — with the following conditions:

1. **Gated**: everything ships behind `tokenExchange.enabled` (ADR 0002 chart appendix); the default posture is static per-MCP credentials, and no preset enables exchange implicitly.
2. **Sequenced last**: implementation begins only after the ADR 0001–0003 enforcement path is shipped and validated. Nothing in that path depends on this feature.
3. **Spike prerequisite (go/no-go gate)**: before implementation, a timeboxed spike in KIND — AIB from its upstream chart, a mock third-party OAuth provider and dummy API in-cluster — walks the full chain end to end: service registration → permission-set binding → ext_proc deny with authorization URL → authorization-code flow against the mock → vault session → successful retry with the exchanged token → session kill → same deny resurfaces. Exit criteria: every step observed, F0 gaps enumerated with workarounds, deny-payload plumbing confirmed. This is the direct lesson of phase 1, where the structural gap was discovered only in live integration; the spike's findings are recorded against this ADR and can still flip it to defer.
4. **UI deferred**: the raw fail/approve/retry flow is the contract; the KAOS UI workflow is a later UX layer that changes nothing underneath.
5. **Re-check trigger**: if Keycloak's identity-chaining (RFC 7523) path reaches supported status with a comparable consent model, re-evaluate the AIB dependency before further investment.

## Consequences

- KAOS gains a credible path to per-user third-party delegation — the capability that closes ADR 0003's deferred "per-user downstream access" item properly (scoped third-party tokens rather than header forwarding).
- The AIB relationship is now fully specified across ADRs: optional issuer adapter (0002) + optional exchange filter (this ADR), never enforcement (0001), permission sets never in the PDP path.
- A new stateful dependency (vault) and its failure modes enter the system — but only in deployments that enable the feature, and every failure mode surfaces through the single fail-with-URL path.
- The F0 upstream gaps become a prerequisite conversation with AIB upstream at implementation time, with the KIND spike quantifying the workaround cost if upstream does not move.
