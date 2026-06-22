# CRD identity override (`spec.security.id`) — implementation plan

**Branch (KAOS)**: `feat/crd-identity-override`, stacked off `feat/extproc-token-exchange`; PR targets `feat/extproc-token-exchange`
**Tracking issue**: axsaucedo/kaos#231

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change -> validate tests pass -> commit (comprehensive, functional message describing WHAT changed; NO phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Push to the PR and validate CI green. Run Go/python tests locally; KIND available — run 1-3 checks locally before relying on CI; prefer the full suite in CI. Be efficient with testing. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null` (create it if missing). Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all prior phases + this work), posted as a PR comment (not committed). Copy this plan to `kaos-ai-docs/security-and-identity/plan/P8-crd-identity-override.md` and write `impl/progress` + `impl/learnings` entries.

## Problem statement

Expose the user-configurable logical security identity. Every earlier phase derives a KAOS resource's logical identity purely from its Kubernetes coordinates: `kaos://{kind}/{namespace}/{name}`. That ties grant continuity to namespace/name and prevents a resource from keeping a stable identity across a namespace move or a rename. P8 adds the first-class `spec.security.id` override on the three identity-bearing kinds (Agent, MCPServer, ModelAPI): when set, the resolved identity becomes `kaos://{kind}/{id}` (namespace-independent); when omitted, the existing `kaos://{kind}/{namespace}/{name}` default is unchanged. Because an explicit id is a shared logical identity, it must be **unique per kind among active resources**: accidental active duplicates are rejected, and a later resource may **adopt** the identity only once the previous holder no longer exists (grant survival across delete/recreate). This is the CRD surface of ADR-KAOS-001 and its pre-implementation collision/adoption follow-up. `spec.security.id` is the **only** per-resource security field — there are deliberately no per-resource auth overrides.

## Current-state grounding (researched)

- **No `spec.security` anywhere.** `AgentSpec` (`operator/api/v1alpha1/agent_types.go:194`), `MCPServerSpec` (`mcpserver_types.go:11`), and `ModelAPISpec` (`modelapi_types.go:98`) have no security block. Requested edges are expressed only through wiring fields (`spec.mcpServers`, `spec.modelAPI`, `spec.agentNetwork`). All three kinds are identity-bearing per ADR-KAOS-001.
- **Logical identity is computed in TWO independent codebases**, both hardcoded to namespace/name:
  - **Operator** (`operator/controllers/agent_controller.go:726`): `buildAgentAuthEnvVars` injects `AIB_ACTOR = fmt.Sprintf("kaos://agent/%s/%s", agent.Namespace, agent.Name)` into the agent pod (the SDK's actor identity). This is the only operator-side identity string. Gated by `security.GetConfig().CredentialMountingEnabled()`. The per-agent credential Secret is named `<prefix>-<agent.Name>` (K8s name, via `cfg.CredentialSecretName`) and the operator mounts it by that name — **this naming is coordinate-based by design and must stay** (operator and sync agree by K8s name regardless of logical id).
  - **Sync service** (`sync-service/kaos_sync/projection.py`): `agent_external_id(ns, name) -> kaos://agent/<ns>/<name>` (the AIB agent `external_id`/`display_name`) and `mcpserver_resource_uri(ns, name) -> kaos://mcpserver/<ns>/<name>` (the resource an agent is authorized against, and the basis for the synthetic service `client_id` `kaos-mcpserver-<ns>-<name>`). `project(resources)` reads only `metadata.namespace`/`name` via `_meta`. The MCPServer edge in an Agent (`spec.mcpServers: [<name>]`) is resolved to a resource URI **by name**, so an MCPServer's own identity and the URI agents are authorized against must resolve identically.
  - ModelAPI projection: added in P5 (`sync-modelapi-edges`); by the time P8 runs it exists and must also honor `spec.security.id`.
- **Sync already has the data it needs.** `K8sResourceLister._list` (`sync-service/kaos_sync/k8s.py:71-84`) returns full custom-object bodies (`result["items"]`), so `metadata.creationTimestamp` and `spec.security.id` are available to the projection for deterministic collision resolution — `_meta` simply does not read them yet.
- **No admission-webhook infrastructure.** `operator/main.go:100` explicitly notes "Webhooks not implemented yet"; there is no `config/webhook`, no cert wiring, no `ValidateCreate`. Adding a webhook would mean cert-manager/Helm/CI plumbing — disproportionate for this phase. Collision/adoption is therefore enforced **without a webhook**: the operator detects conflicts on reconcile and reports them on the resource **status** (loser is not provisioned, never goes Ready), and the sync projection deterministically refuses to project a duplicate active identity. This is "reject accidental active duplicates; allow adoption only when the previous holder is gone."
- **Tests**: sync projection/reconcile unit tests assert the literal `kaos://...` strings (`sync-service/tests/test_projection.py:34-35,57-59`, `test_reconcile.py:81,98`) — these must be extended, and new explicit-id cases added. Operator unit tests live under `operator/...`; e2e under `operator/tests/e2e/` (pytest, KIND).

**Target (ADR-KAOS-001)**: resolution is `id` omitted -> `kaos://{kind}/{namespace}/{name}`; `id` provided -> `kaos://{kind}/{id}`. Explicit ids are unique per kind among active resources; AIB `external_id` uses the resolved identity; grants survive delete/recreate when the resolved identity is unchanged.

## Design plan (how it fits)

### Shared resolution contract (implemented in both codebases)

A single resolution rule, mirrored in Go and Python so both planes agree byte-for-byte:

```
resolveLogicalID(kind, namespace, name, securityID):
  if securityID == "":  return "kaos://" + kind + "/" + namespace + "/" + name
  else:                 return "kaos://" + kind + "/" + securityID
```

`kind` is the lowercase singular (`agent`, `mcpserver`, `modelapi`). The default branch is exactly today's behaviour, so omitting `spec.security.id` changes nothing.

### Operator (Go): CRD surface, resolution, collision/adoption

- **CRD field**: add a shared `SecuritySpec` type (`operator/api/v1alpha1/security_types.go`) with `ID string` (`+kubebuilder:validation:Optional`, `+kubebuilder:validation:Pattern` restricting to a safe path segment — lowercase alphanumerics, `-`, `_`, `.`, no `/` or whitespace, since it is embedded directly after `kaos://{kind}/`). Add `Security *SecuritySpec \`json:"security,omitempty"\`` to `AgentSpec`, `MCPServerSpec`, `ModelAPISpec`. Regenerate deepcopy + CRD manifests + chart CRDs (`make generate manifests`, then sync the chart CRDs the repo's process uses).
- **Resolution helper**: `operator/pkg/identity/identity.go` (new) with `Resolve(kind Kind, namespace, name, securityID string) string` and per-kind helpers. Replace the hardcoded `AIB_ACTOR` value in `buildAgentAuthEnvVars` with `identity.Resolve(identity.KindAgent, agent.Namespace, agent.Name, agent.Spec.Security.GetID())` (nil-safe getter on `*SecuritySpec`).
- **Collision/adoption (status-based, no webhook)**: add a reusable check `identity.DetectConflict(...)` and call it early in each controller's reconcile when `spec.security.id` is set: list all resources of the same kind cluster-wide (operator already has list RBAC on its own kinds), find any **other** resource with the same explicit `spec.security.id`; the **oldest** by `metadata.creationTimestamp` (tiebreak: namespace then name, lexicographic) is the legitimate holder. If the resource being reconciled is **not** the holder, set its status to a conflict state (`Phase: Failed`, `Ready: false`, `Message: "security.id \"<id>\" already in use by <ns>/<name>"`) and **skip** identity-dependent provisioning (no AIB actor env / no SecurityPolicy-relevant identity), then return without error (no requeue storm — re-reconcile happens when the conflicting resource changes; add a watch/no-op is acceptable, but a plain status set + return is the MVP). Adoption falls out naturally: once the older holder is deleted, the remaining resource becomes the holder on its next reconcile and provisions normally.

### Sync service (Python): resolution + collision-safe projection

- **Read more metadata**: extend `_meta` (or add a small `_resource_identity(resource)` helper) to also return `spec.security.id` and `metadata.creationTimestamp`.
- **Resolution helpers**: add `resolve_logical_id(kind, ns, name, security_id)` and route `agent_external_id` / `mcpserver_resource_uri` (and the ModelAPI equivalent from P5) through it. The synthetic service `client_id` must derive from the **resolved** mcpserver identity so the access-check maps consistently (when an explicit id is set, base the client_id on the id, e.g. `kaos-mcpserver-<id>`; keep `kaos-mcpserver-<ns>-<name>` for the default).
- **Edge resolution**: build a `(namespace, mcpName) -> resolved_mcpserver_uri` map from standalone MCPServer resources (reading their `spec.security.id`); when an Agent edge references an MCPServer that has a standalone resource, use its resolved URI; for "ghost" edges (no standalone MCPServer) fall back to the ns/name default (current behaviour).
- **Collision-safe projection**: when two **active** resources of the same kind resolve to the same explicit logical id, keep the **oldest** (by `creationTimestamp`, tiebreak ns/name) and skip the rest; surface the skipped duplicates as conflicts (collect them on `DesiredState`, e.g. `conflicts: list[Conflict]`, so `reconcile`/`main` can log + emit them via the P5 status/metrics surface). This prevents the silent last-write-wins that the current keyed reconcile would otherwise produce. Adoption falls out naturally: a deleted holder is pruned (P5), freeing the id for the surviving resource on the next cycle.
- **Reconcile/main**: thread the conflict list into the P5 status/observability surface (a log line + a `kaos_sync_identity_conflicts` gauge/counter, and the status object if present). No behavioural change when there are no explicit ids.

### Samples + docs

- Add/extend a sample showing `spec.security.id` for an Agent (and one MCPServer) demonstrating a stable, namespace-independent identity.
- Document the identity model + the override + the collision/adoption rule in the security docs.

## Numbered TODOs

1. **CRD `spec.security.id` surface.** Add `operator/api/v1alpha1/security_types.go` with `SecuritySpec{ ID string }` (`Optional` + `Pattern` safe-segment) and a nil-safe `GetID()` method on `*SecuritySpec`. Add `Security *SecuritySpec` to `AgentSpec`, `MCPServerSpec`, `ModelAPISpec`. Run `make generate manifests` and propagate the regenerated CRDs into the operator chart per the repo's existing CRD-sync process (`operator/chart/...`). **Validate**: `cd operator && make generate manifests` produces deepcopy + CRD changes with no unrelated drift; `go build ./...`; `kubectl apply --dry-run=server` (or `--dry-run=client` if no cluster) of the regenerated Agent CRD accepts `spec.security.id` and rejects an id containing `/`.

2. **Operator identity resolution + actor wiring.** Add `operator/pkg/identity/identity.go` with `Kind` constants (`agent`/`mcpserver`/`modelapi`) and `Resolve(kind, namespace, name, securityID) string` implementing the shared rule. Replace the hardcoded `AIB_ACTOR` value in `buildAgentAuthEnvVars` (`agent_controller.go`) with the resolver using `agent.Spec.Security.GetID()`. Add `identity_test.go`: default vs explicit for each kind; empty-id default; id with dots/dashes. **Validate**: `cd operator && go test ./pkg/identity/... && make test-unit`; confirm an Agent with `spec.security.id: researcher` yields `AIB_ACTOR=kaos://agent/researcher` and one without yields `kaos://agent/<ns>/<name>` (unit-assert the env builder); `gofmt -l`/`go vet ./...`.

3. **Operator collision/adoption + status.** Add `identity.DetectConflict(ctx, client, kind, self)` (lists same-kind resources, returns the legitimate holder by oldest `creationTimestamp` + ns/name tiebreak). In each controller (`agent`/`mcpserver`/`modelapi`), when `spec.security.id` is set, run the check early: if `self` is not the holder, set status `Phase=Failed`, `Ready=false`, `Message="security.id \"<id>\" already in use by <ns>/<name>"` and skip identity-dependent provisioning; otherwise proceed normally. **Validate**: add controller/`envtest` (or table-driven unit) cases: two Agents same explicit id -> older is Ready/provisioned, newer is Failed with the conflict message; delete the older -> newer becomes the holder on re-reconcile (adoption); distinct ids -> both Ready; omitted id -> unchanged behaviour. `make test-unit`; `make manifests generate` clean; `go vet ./...`.

4. **Sync projection: resolution + collision-safe.** In `sync-service/kaos_sync/projection.py` add `resolve_logical_id(kind, ns, name, security_id)`, route `agent_external_id`/`mcpserver_resource_uri`/`service_client_id` (and the P5 ModelAPI projection) through resolved ids, extend `_meta`/add `_resource_identity` to read `spec.security.id` + `creationTimestamp`, build the `(ns, mcpName) -> resolved URI` edge map, and add collision-safe dedup (keep oldest active per `(kind, explicit_id)`, skip duplicates, collect `conflicts` on `DesiredState`). **Validate**: extend `tests/test_projection.py` — explicit-id agent -> `kaos://agent/<id>`; explicit-id mcpserver -> agent edge authorizes against `kaos://mcpserver/<id>` and service `client_id` derives from the id; two agents same explicit id -> only the oldest projected, the other recorded as a conflict; default (no id) unchanged. `cd sync-service && source .venv/bin/activate && python -m pytest tests/ -v && make lint` (or the repo's sync lint).

5. **Sync conflict surfacing.** Thread `DesiredState.conflicts` through `reconcile.py`/`main.py` into the P5 status/observability surface: a clear log line per conflict and a `kaos_sync_identity_conflicts` metric (and the status object if P5 exposes one); no change when there are no explicit ids/conflicts. **Validate**: extend `tests/test_reconcile.py` (and any main/status test) to assert conflicts are reported and the losing duplicate is not reconciled into AIB; `python -m pytest tests/ -v && make lint`.

6. **Samples + docs.** Add a sample manifest set under the operator/CLI samples demonstrating `spec.security.id` (an Agent with a stable id; an MCPServer with a stable id and an Agent edge to it). Document the identity model, the `spec.security.id` override, the resolution table, and the collision/adoption rule in the security docs (and, if present, the identity section of `docs/`). **Validate**: `kubectl apply --dry-run=client -f <sample>` accepts the manifests; docs build if the repo builds docs in CI (`cd docs && npm run build`), else markdown-only (no build needed); confirm samples lint/validate via any existing sample-validation test.

7. **End-to-end + docs + PR/REPORT.** On local KIND with `--auth-enabled`, validate end to end: (a) an Agent with `spec.security.id: researcher` resolves to `kaos://agent/researcher` in AIB (sync) and as `AIB_ACTOR` in the pod (operator), and its grant **survives delete/recreate** (recreate in a different namespace with the same id -> same AIB record adopted, grant intact); (b) two active Agents with the same explicit id -> the newer is rejected (status Failed; not projected into AIB); (c) an MCPServer with an explicit id -> an Agent edge to it authorizes against the resolved URI and the call is allowed via `ext_authz`; (d) resources without `spec.security.id` behave exactly as before (regression). Suppress output to `./tmp/null`; run 1-3 e2e locally first. Write `impl/progress/P8-*.md` + `impl/learnings/P8-*.md`, copy this plan to `plan/P8-crd-identity-override.md`. Push `feat/crd-identity-override`, open the stacked PR into `feat/extproc-token-exchange`, dispatch `go-tests`/`python-tests`/`e2e` on the branch, confirm CI green, write the gitignored `REPORT.md` (P0–P8) and post it as a PR comment.

## Validation per task

- Per-TODO: operator `go test ./...` (targeted package first) + `make test-unit` + `make generate manifests` (deepcopy/CRD drift expected only in T1; none elsewhere); sync `pytest` + lint; samples `kubectl --dry-run`; docs build only if CI builds docs.
- The full identity e2e (resolution + adoption + duplicate rejection) is **local-KIND** with `--auth-enabled` (broker/sync unpublished); document results in `REPORT.md`. The existing security-off suites must stay green — `spec.security.id` is optional and the omitted path is byte-identical to today.
- Push the stacked PR and dispatch `go-tests.yaml` / `python-tests.yaml` / `e2e-tests.yaml` via `workflow_dispatch --ref feat/crd-identity-override`.

## Commit / PR strategy

- `feat/crd-identity-override` stacked off `feat/extproc-token-exchange`; one comprehensive, functional commit per TODO; PR into `feat/extproc-token-exchange`; keep CI green; Copilot co-author trailer on KAOS commits (kaos-ai-docs commits follow that repo's no-trailer convention).
- Push under the `axsaucedo` gh account; **keep the commit author as the repo default** — do NOT override author email when switching gh accounts. Restore the EMU account after.
- `REPORT.md` gitignored; contents posted as a PR comment.

## Out of scope (later phases)

- Shared-identity / intentional cross-namespace adoption beyond "adopt only when the previous holder is gone" (a future explicit shared-identity feature).
- An admission webhook for synchronous apply-time rejection (status-based rejection is the MVP; a webhook can harden it later if needed).
- Any per-resource `authentication`/`authorization`/public override fields — `spec.security.id` is deliberately the only per-resource security field.
- Kubernetes cluster identity in the logical id; ServiceAccount/SPIFFE workload-to-identity binding (ADR-KAOS-001 accepted constraints).
- Run-scoped / autonomous-run-bound identities (deferred per ADR-KAOS-001 / ADR-KAOS-006).
- SDK token-lifecycle productionisation (P9); sync productionisation/extraction (P10).
