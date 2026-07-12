# P19 — The model and the user plane: subject-required rego, AccessGrant, DCR, Keycloak

**Status**: In progress
**Date**: 2026-07-12
**Realises**: [ADR 0003](../adrs/adr_0003_authorization-model-and-data-schema.md) (user + agent + resource model) + [ADR 0002](../adrs/adr_0002_agent-identity-issuers-and-aib-boundary.md) DCR half
**Branch/PR**: stacked on the P18 branch (`feat/kaos-pdp-ext-authz`) until it merges, then rebased to `main`. Commit/branch/PR text never references task or phase numbers.

## What P18 already delivered (the foundation this builds on)

- `policy.rego` (`package kaos.authz`): actor-only decision, fail-closed. Verifies the actor token (RS256 + iss + `kaos-gateway` aud + signature against `data.kaos.jwks`), resolves `sub`→actor id via `data.kaos.agents[id].issuer_sub`, then `target_resource in data.kaos.grants[actor_id]`. Target resource derived **only** from the operator-owned route path.
- `data.kaos.*`: `grants` (actor→resources incl. memorystore), `jwks` (multi-issuer), `agents` (id → `{issuer_sub}`).
- Issuer abstraction `security.agentAuth.identity.provider: serviceaccount|oidc|aib` — `serviceaccount` and `aib` implemented; **`oidc` is the DCR path this phase adds**.
- Gateway dual JWT providers (`agent` implemented; `user` provider generation exists for the Keycloak presets). Subject propagation exists in the runtime (`kaos_identity/instrument.py`): inbound `Authorization` subject forwarded unchanged, actor always local.
- `PolicyProjector` seam (`controllers/authz_projection_controller.go`); `BrokerProjector` (AIB) and the SA-issuer JWKS/mapping projection are the existing adapters.
- `Agent.spec.autonomous` (Goal-activated self-loop) already on the CRD.

## Design note — how P19 fits

The model change is confined to two artifacts plus their data sources: the **rego** (subject-required conjunction) and the **`data.kaos.*` schema** (`user_grants`, `agents[id].autonomous`). Enforcement topology, header plumbing, and delivery are unchanged from P18. The user plane is additive: with no user IdP, `kaos-internal` keeps working exactly as today (subject = the autonomous/agent self-token path), and `AccessGrant`s are accepted-but-unenforced. New operator surface: the `AccessGrant` CRD + its compiler, the `OIDCProjector` (DCR), and the Keycloak group-mapper provisioning.

## TODOs (in order; one commit per task; RUN rego via operator/bin/opa and CI gates locally before pushing)

1. **`AccessGrant` CRD (namespaced)**: `spec.subjects[]` (`kind: User|Group`, `name`) and `spec.resources[]` (explicit `kind`+`name`, or a label `selector`). Types + deepcopy + CRD manifest + RBAC (`make manifests`). Status conditions supported. No admission webhook.
2. **AccessGrant compiler → `data.kaos.user_grants`**: a new projector (behind the `PolicyProjector` seam) compiling AccessGrants into `{"group:/x": ["kaos://.../..."], "user:a@b": [...]}`. When no user IdP is configured: set the grant's status condition `Enforced=False`, `reason=NoUserIdentityProvider`, emit a warning event, and **skip** projecting user-subject grants. When the user plane is enabled, flip to enforced on the next reconcile (no object change).
3. **Project `data.kaos.agents[id].autonomous`**: extend the SA/identity projection to emit `autonomous: true|false` from `Agent.spec.autonomous`, alongside the existing `issuer_sub`.
4. **New rego — subject-required conjunction**: a subject is ALWAYS required (deny if absent). Subject may be (a) a verified **user** token (Keycloak issuer/aud), or (b) a verified **agent** token whose `data.kaos.agents[id].autonomous == true` (autonomous self-subject). Entry-edge vs internal-hop: at the entry edge (subject present, actor absent) require a user subject with an `AccessGrant` covering the target; on internal hops (actor present) authorize on the actor's grant, with the propagated subject verified and required but not needing a per-resource AccessGrant. Both tokens verified in-policy. Keep all P18 fail-closed properties. RUN new rego cases: user+grant→allow at entry, user-no-grant→deny, autonomous self-subject→allow, non-autonomous self-subject→deny, no-subject→deny.
5. **Autonomous self-subjecting in the runtime**: when the autonomous loop starts (`kaos_identity` / pais autonomous path), seed the propagation context's subject slot with the agent's own actor token. Non-autonomous agents never self-subject. Unit tests.
6. **Entry vs internal route policy attachment**: ensure externally-attached routes carry the user JWT provider and the entry-edge policy; internal routes keep the agent-plane policy. Add the CI invariant test that an externally attached route always carries the entry policy. Confirm the token-shape signal (actor absent = entry) and route/listener classification agree.
7. **`OIDCProjector` (RFC 7591/7592 DCR)**: provider-generic client-per-agent registration via Dynamic Client Registration, Secret delivery, bootstrap-token wiring; selected by `identity.provider=oidc`. Behind the same `PolicyProjector` seam. Keycloak supports DCR natively.
8. **Keycloak group-membership protocol mapper**: chart provisions the `groups` claim mapper in the Keycloak-provisioning presets (it already creates realm+client); document it as a hard requirement for bring-your-own-Keycloak (without it, group `AccessGrant`s silently never match — the forbidden state).
9. **Preset wiring**: Keycloak-backed presets enable subject verification + `AccessGrant` enforcement over the same PDP; expose `identity.provider=oidc` for DCR agent clients. CLI tests for the expansions.
10. **Validation**: full unit suites + rego (RUN) + chart render + KIND e2e user+agent+resource matrix (user-with-group-grant reaches agent; user-without denied at entry; autonomous agent operates self-subjected; non-autonomous self-subject denied; internal hop carries+verifies propagated subject; `AccessGrant` shows `Enforced=False` in `kaos-internal` and flips when `userAuth` enabled). Never delete the existing KIND cluster.
11. **Docs in lockstep**: update `walkthrough-user-identity.md` and `walkthrough-auth.md` to describe the shipped user plane + `AccessGrant` (remove the "forthcoming" markers now made true); document the model, `data.kaos.user_grants` schema (align `data-schema.md`), the group-mapper requirement, and the honest "does not support" list (per-user downstream authorization deferred, ~90s propagation incl. revocations).
12. **REPORT.md** (gitignored, never committed): thorough task-by-task status; posted as the PR comment.

## Review round (mirrors P18's proven close-out)

13. **Codex reviewer pass**: launch a fresh `codex exec` session (never the implementing session) at sol high with a ranked-findings brief scrutinizing the new rego (subject/actor conjunction, entry vs internal classification spoofability, autonomous self-subject soundness, empty-mapping/empty-grants bypasses, fail-closed edges), the AccessGrant compiler (unenforced-state correctness), and DCR credential handling. End-marker.
14. **Apply review fixes**: orchestrator verifies EVERY finding in code (do not trust Codex's word); security/functional fixes as individual commits, cleanups batched; run CI gates locally (full-project `ty`, real `opa test`) before pushing.
15. **Close out**: full suites green + CI green; push; update REPORT.md with the findings/resolutions table; post as PR comment; reply on any inline review threads.

## Dependency and sequencing

Strictly linear within the phase: CRD (1) → compiler (2) + autonomous projection (3) → rego (4) → runtime self-subject (5) → route attachment (6) → DCR (7) + Keycloak mapper (8) → presets (9) → validation (10) → docs (11) → review (13-15). Each task is individually committed; the branch stays demoable.
