# Multi-tenancy, scope enforcement, and governance — implementation plan

> **STATUS: COLLAPSED — not executed as a standalone milestone.** An assessment against the shipped code found that M5's safety-critical surface was already delivered by M3/M4 and that its enforcement point is provided by the gateway/identity track, so executing this plan as written would re-implement existing behaviour. See the M5 section of [`proposed-split.md`](./proposed-split.md) for the evidence and the deferred non-synthetic follow-ups. Summary of what already exists: the `scope`/`tools`/`failureMode` Agent surface and `MEMORY_*`/`AGENT_IDENTITY` env (M4); fail-closed scope resolution (`Scope.owner_kwargs()` raises on an incomplete scope; `scope_from_deps` rejects `private` without an owner); complete three-tier erasure (`ShortTermStore.clear()` + `LongTermStore.delete_scope()`); and gateway-routed memory traffic through the identity-integrated gateway. Deferred, non-synthetic follow-ups: (a) reconcile ADR-0005/ADR-0001 wording to the flat four-value scope model (docs pass); (b) A2A delegation service-tier context propagation and admin cross-user erasure, which depend on per-request user-principal propagation from the identity track. The original plan is preserved below for historical reference.


**Branch (KAOS)**: `feat/memory-multitenancy`, stacked off the later of `feat/memory-runtime-client` (M3) and `feat/memory-store-crd` (M4); PR targets that tip.
**Tracking issue**: TBD (do not reference in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md): `{M3, M4} → M5 → M7`. M5 closes the cross-cutting tenancy/governance model that spans the service, the runtime, and the operator, so it stacks on whichever of M3/M4 lands last (it needs both the runtime scope plumbing and the CRD/Agent block). **Before starting, re-read [`../impl/learnings/M3-runtime-client.md`](../impl/learnings/M3-runtime-client.md) and [`../impl/learnings/M4-memory-store-crd.md`](../impl/learnings/M4-memory-store-crd.md)** and confirm the live scope-plumbing and `MEMORY_*` env shapes.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run unit tests across the touched components locally (`memory-service`, `pydantic-ai-server`, `operator`); push the PR and confirm CI green. Alpha: breaking changes OK.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all prior phases + this work) posted as a PR comment (not committed). Copy this plan to `plan/M5-multitenancy.md` and write `impl/progress/M5-*.md` + `impl/learnings/M5-*.md`.

## Problem statement

Make memory isolation **non-optional and fail-closed**, and add the lifecycle governance the target requires ([adr_0005](../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md)). Specifically: surface the three-value `scope` enum (`private | user | shared`) on the Agent memory block and map it onto Mem0's owner filter keys in the service; make scope resolution mandatory at the service so a request that cannot resolve a trusted scope **fails rather than querying an unscoped store**; bind A2A delegation propagation so a delegate inherits the delegator's scope prefix (shared-above, isolated-below) injected server-side through `DelegationToolset`, overridable to full-share or full-isolation; implement **synchronous scope-targeted right-to-erasure** that fans out across both tiers (short-term table by scope prefix, Mem0 delete filtered by scope, rolling-summary clear) with no shadow copy left behind; and confirm audit rides existing OpenTelemetry. Store-per-tenant isolation is **emergent** (deploy multiple `MemoryStore`s) and needs no new field.

## Current-state grounding (researched)

- M1 shipped the `Scope`→Mem0-filter-keys mapping as a correct translation but **not** as enforcement; M2 trusts a `scope` block in the request; M3 derives scope server-side from `AgentDeps` and attaches it. M5 makes the service reject unresolved scope and removes any client-trust path.
- The `scope` enum is owned by [adr_0005](../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md) and was deliberately **not** added to the slim Agent block in M4 — M5 adds `scope: private|user|shared` to the Agent memory block and plumbs it to the service as request policy.
- A2A delegation hand-off is `pais/tools.py` `DelegationToolset` (`:55-108`, `:130-144`), where the delegator forwards short-term context to sub-agents; M3 made it carry the delegated scope context, M5 fixes the inheritance policy (prefix shared-above/isolated-below, server-injected, overridable).
- Erasure must leave no shadow copy: [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md) disables Mem0's local SQLite change-history log, so a scoped delete on the short-term table + a Mem0 scoped delete + a rolling-summary clear is complete ([adr_0005](../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md)).
- Mem0's isolation is application-level filtering with no row-level security ([adr_0002](../adrs/adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md)), so the **service is the sole fail-closed enforcement point**; the runtime and operator only supply the trusted scope.

## Design plan (how it fits)

- **Scope enum on the Agent block + plumb-through.** Add `scope: private|user|shared` (default `private`) to the slim Agent `MemoryConfig` (operator types + `make generate manifests`), set it into a `MEMORY_SCOPE` env, have M3's `scope_from_deps` read it, and pass it as the selector in the request scope block.
- **Mandatory fail-closed resolution in the service.** In M2's scope handling, require a fully-resolved trusted scope (principal/agent `client_id`/selector consistent) on every `recall`/`write`/`forget`; if it cannot be resolved, **reject** (HTTP 4xx + a fail-closed span) rather than querying an unscoped store. Remove any path that reads scope from untrusted body fields beyond the server-injected block. The `shared` selector still resolves to a store-wide query — that is an explicit, configured decision, not an unresolved scope.
- **A2A scope inheritance.** In `DelegationToolset`, when an agent delegates, the server injects the delegator's scope prefix into the delegate's request context — shared above the divergence point, isolated below — overridable per delegation edge to full-share (identical scope) or full-isolation (delegate's own private scope). The delegate never trusts a client-supplied scope; the prefix is computed server-side from the delegator's resolved scope.
- **Synchronous scope-targeted erasure.** Complete M2's `/v1/forget` into the guaranteed cross-tier fan-out: delete short-term rows by scope prefix, `LongTermStore.delete(scope)` (Mem0 scoped delete), clear the rolling summary for that scope; synchronous and best-effort-but-verified, returning a per-tier deletion summary. Confirm no Mem0 change-history shadow remains (log disabled per [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md)).
- **Audit via OTel.** Ensure each enforcement decision and erasure emits a span/event on the existing telemetry path; no separate audit store ([adr_0005](../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md)).
- **Store-per-tenant = emergent.** Document that physical isolation is achieved by deploying multiple `MemoryStore`s and pointing tenant agents at their own `storeRef`; no isolation-mode field is added.

## Numbered TODOs

1. **Scope enum on the Agent block + env.** Add `scope: private|user|shared` (default `private`) to the slim Agent `MemoryConfig`; `make generate manifests`; set `MEMORY_SCOPE` in `agent_controller.go`; have M3 read it in `scope_from_deps`. **Validate**: operator envtest — the enum validates and sets the env; runtime unit test — the selector flows into the request scope; `cd operator && make test-unit` and `cd pydantic-ai-server && pytest tests/ -k scope -v`.

2. **Mandatory fail-closed scope resolution in the service.** Require a fully-resolved trusted scope on `recall`/`write`/`forget`; reject unresolved scope with a 4xx + fail-closed span; remove untrusted scope-read paths; keep `shared` as an explicit resolved selector. **Validate**: `memory-service` tests — unresolved/inconsistent scope is rejected (never queries unscoped), `private`/`user`/`shared` resolve to the right Mem0 filter, two scopes cannot read each other's private items; `cd memory-service && pytest tests/test_enforcement.py -v`.

3. **A2A scope inheritance in delegation.** Implement server-side prefix inheritance in `DelegationToolset` (shared-above/isolated-below default; per-edge override to full-share/full-isolation); compute the prefix from the delegator's resolved scope; never trust client scope. **Validate**: runtime tests — default inheritance shares the prefix and isolates below, override modes behave, a delegate cannot widen its own scope; `cd pydantic-ai-server && pytest tests/test_delegation_scope.py -v`.

4. **Synchronous scope-targeted erasure fan-out.** Complete `/v1/forget` into the guaranteed short-term-delete-by-prefix + Mem0 scoped delete + rolling-summary clear, returning a per-tier summary; assert no change-history shadow. **Validate**: `memory-service` tests — erasure removes exactly the scope's items from both tiers and the summary, other scopes untouched, the returned summary is accurate; `cd memory-service && pytest tests/test_erasure.py -v`.

5. **Audit spans + store-per-tenant docs.** Ensure enforcement decisions and erasures emit OTel spans/events on the existing path; document the emergent store-per-tenant pattern (multiple `MemoryStore`s, per-tenant `storeRef`) in the service/operator notes. **Validate**: tests assert the spans via an in-memory exporter; `pytest` across touched suites + lints.

6. **Cross-component e2e + PR.** Extend the memory e2e: two agents with different scopes pointed at one store cannot read each other's private memory; a delegation inherits the configured prefix; a scoped erasure removes exactly that scope. Reuse `conftest.py`; suppress to `./tmp/null`. **Validate**: e2e green on local KIND and via `workflow_dispatch`. Write `impl/progress/M5-*.md` + `impl/learnings/M5-*.md`, copy this plan, push `feat/memory-multitenancy`, open the stacked PR, confirm CI green, write the gitignored `REPORT.md` (M0–M5) and post it as a PR comment.

## Validation per task

- Per-TODO: run the touched suites — `memory-service` `pytest`, `pydantic-ai-server` `pytest && make lint`, `operator` `make test-unit` — and the relevant lints. The enforcement, delegation, and erasure tests are the load-bearing ones; keep them exhaustive (cross-scope leakage is a security property).
- The cross-component e2e is KIND-based; run a minimal local check first, then the full suite via `workflow_dispatch --ref feat/memory-multitenancy`.

## Commit / PR strategy

- `feat/memory-multitenancy` stacked on the later of M3/M4; one comprehensive commit per TODO; Copilot co-author trailer; CI green. `REPORT.md` gitignored, posted as a PR comment.

## Out of scope (later phases)

CLI install integration and samples (M6); HA tuning, metrics endpoint, the durable-queue decision, and docs (M7). Explicitly deferred by [adr_0005](../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md): dynamic cross-cutting agent groups (a `MemoryGroup` membership-indirection layer — per-user grouping is already dynamic), per-tenant rate/fair-share quotas, logical export/import, application-level encryption, and proof-of-deletion ledgers.
