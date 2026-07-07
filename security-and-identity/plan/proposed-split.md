# Proposed work split and sequencing

## Purpose

This is the master implementation plan for KAOS↔AIB coarse authorization. It sequences the work settled in the [ADR set](../adrs/adr_high_level_components.md) into numbered phases with per-phase TODOs, validation, and commit/CI strategy. It **supersedes the earlier P0–P15 split**, which assumed the abandoned AIB ext_authz decision service (PR #398) and separate Python SDK (PR #399); those phase files remain in this folder as historical record. KAOS is in **alpha**: breaking changes are acceptable and migrations are not documented.

## Guiding principles for the split

- **One engine, one hook.** All authorization runs through OPA embedded in the AIB ext_proc filter ([ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md)). Both models differ only in the data OPA reads.
- **Custom code = AIB admin API only.** A shared pure projection core feeds both models; the Model-2 AIB adapter is the only bespoke integration; Model 1 is pure serialisation ([ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md)).
- **Fold, don't add.** The standalone sync-service is folded into the operator, not kept as a second deployable.
- **Bottom-up, each phase shippable.** Each phase is an independently reviewable increment validated locally and in PR CI before the next begins.
- **Keep it simple.** Prefer the smallest correct mechanism (static `policy.path`, ConfigMap delivery, owner-reference GC) and defer optional sophistication (bundle hot-reload, gateway actor-JWT provider) to [followups](./followups.md).

## Current-state baseline (what already exists)

- **Build target:** AIB `main` (includes #222, OPA-in-ext_proc) **plus PR #397** (deployability: public images, Helm chart, KIND target, optional ext_proc deployment). #397 is rebased onto latest `main` and mergeable. PRs #398 and #399 are abandoned but **not closed**.
- **Operator:** single controller-runtime manager; typed CRDs (Agent, MCPServer, ModelAPI). Renders the ext_proc `EnvoyExtensionPolicy` and the ext_authz `SecurityPolicy`; controllers already gate on `IsOperational() || ExtProcEnabled()`. `IsOperational() == (ExtAuthzURL != "")` also gates credential mounting and NetworkPolicy — a coupling this plan must break.
- **Sync-service:** separate Go module and deployable; controller-runtime manager with a whole-world sentinel reconciler; projects services/permission-sets/agents/credentials to the AIB admin API; mints and writes the per-agent credential Secret that the operator only mounts (split-brain). PR #260 adds agent→agent access-edge projection.
- **Runtime:** `pydantic-ai-server/aib/` mints the actor token via `client_credentials` and injects `authorization` (subject) and `x-agent-authorization` (actor) headers. Provider-agnostic client, AIB-automated path.

## The proposed phases

Each phase lists numbered TODOs. A per-phase detail file (`plan/<phase>-*.md`) is fleshed out as the phase begins, and per-phase progress/learnings are recorded under `impl/progress/` and `impl/learnings/`.

### P1 — Security-config foundation ([ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md))

Decouple the "security enabled" predicate from `ExtAuthzURL` so later phases can make ext_authz optional without silently disabling credentials and NetworkPolicy, and introduce the authorization-mode and enforcement-posture configuration surface.

1. Introduce a broader `SecurityEnabled` predicate (distinct from `ExtAuthzURL != ""`) and re-gate credential mounting and NetworkPolicy on it.
2. Add config for authorization **model** (model 1 / model 2 / both), **enforcement posture**, **verification mode**, and **populator mode**, defaulting to the simplest safe values.
3. Unit-test the predicate and config parsing, including the "ext_authz off but security on" combination.

Validation: `cd operator && make test-unit`, `go vet ./...`, `gofmt`.

### P2 — Fold the sync-service into the operator ([ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md))

Relocate the projection core and AIB admin client into the operator module as a second controller, and delete the standalone deployable.

4. Move `projection`, `aib` client, and the whole-world sentinel reconcile into the operator module as an `AIBProjectionReconciler`; convert unstructured reads to typed CRD clients.
5. Register the projection controller as a second controller in the operator manager, isolated from the workload reconciler (which never calls AIB).
6. Make the operator the sole minter/writer of the credential Secret with `ownerReference: Secret → Agent`; delete the bespoke `pruneSecrets()` in favour of owner-reference GC.
7. Delete the sync-service deployable, its Helm chart/image/CI job, and its Go module; remove duplicated `kaos-aib-<name>` naming by sharing one helper.

Validation: `cd operator && make generate manifests test-unit`; confirm chart renders without the sync-service; targeted e2e that an Agent still gets its credential Secret.

### P3 — Shared projection core ([ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md))

Make `Project() → DesiredState` model-agnostic so Model 1 and Model 2 are thin adapters.

8. Strip AIB-specific `AdminBody()` serialisation off `DesiredState` into a Model-2 adapter package; keep `DesiredState` a pure grant graph keyed by the logical identities from [ADR 0002](../adrs/adr_0002_identity-and-authentication.md).
9. Verify at implementation that the broker stamps the `client_credentials` token `sub` as the logical identity (not an internal UUID); if UUID, key data by UUID or add a UUID→logical map. Record the finding in `impl/learnings/`.
10. Unit-test the pure core and the Model-2 adapter separately.

Validation: `cd operator && make test-unit`.

### P4 — Model 1 emitter and JWT verification ([ADR 0002](../adrs/adr_0002_identity-and-authentication.md), [ADR 0003](../adrs/adr_0003_authorization-models-and-policy-data.md))

Emit the Model-1 OPA data and wire the ext_proc OPA on.

11. Ship the generic static rego as an operator asset: keys on the actor identity and the requested resource, checks `data.kaos.grants`, and branches on `data.kaos.jwks` presence (`decode_verify` if present, else `decode`).
12. Render `DesiredState → data.json` and write it (plus the rego) into a ConfigMap mounted into the AIB ext_proc pod; wire OPA `policy.path`, `policy.package`, `policy.decision` via the #397 chart values.
13. Inject `data.kaos.jwks` into the data ConfigMap only when an issuer is configured (verified mode); leave it out in demo mode.
14. Publish the `data.kaos.grants` (and `data.kaos.jwks`) schema as a documented public contract.

Validation: `cd operator && make test-unit` for the emitter; targeted e2e that a mounted grant allows and a missing grant denies (demo mode) and that verified mode rejects an unsigned actor token.

### P5 — Enforcement posture and ext_authz generalisation ([ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md))

Make ext_proc OPA the default and keep ext_authz as an optional seam.

15. Make the ext_proc OPA the default enforcement path; ensure controllers enable it under `SecurityEnabled`.
16. Generalise the ext_authz `SecurityPolicy` generation off the AIB-#398 assumption into an optional, default-off seam pointing at a configurable backend (for a KAOS-run OPA in AIB-less setups; the KAOS-run OPA itself is [followup F1](./followups.md)).
17. Remove the `ExtAuthzUrl`-as-only-switch assumptions left after P1; keep the user-auth JWT authn, NetworkPolicy, and ext_proc EnvoyExtensionPolicy intact.

Validation: `cd operator && make test-unit`; chart-render tests for default-off ext_authz; targeted e2e enforcing via ext_proc OPA with no ext_authz.

### P6 — Populator / override modes ([ADR 0003](../adrs/adr_0003_authorization-models-and-policy-data.md))

Implement the source-of-truth modes with the prune-safety invariant.

18. Default CRD projection (P-crd) for both models (authoritative).
19. Model-1 **M1-a** (bring-your-own ConfigMap): operator points `policy.path` at an admin-provided ConfigMap and does not manage its contents.
20. Model-1 **M1-b** (operator-rego + admin data): operator owns the `policy.rego` key via server-side-apply field ownership and never writes the `data.kaos.grants` key.
21. Model-2 **external off-switch**: disable authorization projection and **force prune off**; KAOS keeps identity (agent registration + credential Secret); enforcement reads AIB live via `granted_permission_sets`.
22. Enforce the prune-safety invariant: apply/prune are mode-gated; a test proves the operator leaves admin-owned data untouched across reconciles.

Validation: `cd operator && make test-unit`; e2e per mode including the "no-clobber across reconciles" assertion.

### P7 — Framework enablement (chart + CLI)

Expose the configuration through the chart and `kaos` CLI.

23. Add Helm values for model selection, enforcement posture, verification mode, and populator mode; wire them to the operator config from P1.
24. Add `kaos system install` flags (and any `kaos`-side helpers) that set those values; keep defaults simple and safe.
25. CLI dry-run/integration tests validating the rendered YAML for each combination.

Validation: `cd kaos-cli && python -m pytest tests/ -v`; chart-render tests.

### P8 — Tests, docs, and examples

Prove every mode end-to-end and document it.

26. E2E matrix on KIND: both models; demo vs verified; M1-a, M1-b, Model-2 off-switch; deny/allow and no-clobber assertions. Prefer PR CI for the full suite; run 1–3 locally first.
27. Docs with worked examples for each mode and the published `data.kaos.grants`/`data.kaos.jwks` schema; explicitly fence demo mode as non-production.
28. Update `.github/copilot-instructions.md` and relevant `.github/instructions/*` to reflect the folded architecture and the authorization modes.

Validation: full PR CI (unit + E2E); Python `make lint`; operator `make test-unit`.

### P9 — ADRs finalised and plan closed

29. Move the [ADR set](../adrs/adr_high_level_components.md) from Proposed to Accepted post-hoc; ensure the historical note in [ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md) accurately records the evolution off #398/#399.
30. Ensure this plan and [followups](./followups.md) reflect the final built state; record per-phase learnings under `impl/learnings/`.

## AIB-side work

There is **no upstream contribution track** anymore. The only AIB dependency is: AIB `main` (with #222) plus PR #397 (deployability), already rebased and mergeable. PRs #398 and #399 stay open-but-abandoned (do not close). No AIB code changes are required for the initial cut; the actor-JWT gateway provider (V2) and any autonomous-mode OPA change are [followups](./followups.md).

## Sequencing at a glance

```
P1 security-config foundation
  └─ P2 fold sync-service into operator
       └─ P3 shared projection core
            └─ P4 Model 1 emitter + JWT verification
                 └─ P5 enforcement posture + ext_authz seam
                      └─ P6 populator / override modes
                           └─ P7 framework enablement (chart + CLI)
                                └─ P8 tests + docs + examples
                                     └─ P9 ADRs finalised + plan closed
```

P1→P9 are largely serial (each builds on the prior). Within a phase, TODOs are ordered; the Model-2 adapter work (P3) and the Model-1 emitter (P4) share the core from P3.

## Cross-cutting notes

- **Prune-safety invariant** (from [ADR 0003](../adrs/adr_0003_authorization-models-and-policy-data.md)): external/manual modes never prune or clobber admin-owned config; enforced from the first prune-capable phase (P2/P6), not retrofitted.
- **Failure isolation** (from [ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md)): the projection controller is the only AIB caller; broker outage stalls only projection, never workloads or health probes.
- **Demo vs verified** (from [ADR 0002](../adrs/adr_0002_identity-and-authentication.md)): demo mode is spoofable and must be documented as non-production; verified mode is the real posture.
- **Commit discipline:** comprehensive conventional commits with no phase/task/ADR-as-task references in messages, branches, or code.

## Explicitly later / out of the critical path

See [followups](./followups.md): F1 AIB-less agent-identity issuer (Keycloak-per-agent vs K8s ServiceAccount token, plus KAOS-run standalone OPA), F2 Python SDK consolidation, F3 autonomous-mode enforcement (G1), F4 ConfigMap bundle hot-reload, F5 V2 gateway actor-JWT provider.

## Progress and learnings tracking

Per-phase progress is recorded under `impl/progress/` and durable findings under `impl/learnings/` (already seeded by [the model-parity learnings](../impl/learnings/opa-extproc-authz-model-parity-and-oauth-path.md)). Each phase updates its status here as it completes.
