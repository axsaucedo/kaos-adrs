# Control plane: MemoryStore CRD and operator reconciliation — implementation plan

**Branch (KAOS)**: `feat/memory-store-crd`, stacked off `feat/memory-service` (M2); PR targets `feat/memory-service` (or M3's tip if M3 lands first — see stacking note).
**Tracking issue**: TBD (do not reference in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md): `M2 → {M3, M4} → M5`, and `M4 → M6`. M4 makes the operator deploy and operate the M2 service declaratively. It is a **sibling** of M3 off M2; whichever lands first, the other rebases onto its tip. The only cross-cutting surface with M3 is the env contract the operator sets for the runtime (the slim Agent memory block → `MEMORY_*` env M3 reads) — keep them matched. **Before starting, re-read [`../impl/learnings/M2-memory-service.md`](../impl/learnings/M2-memory-service.md)** (the service image, readiness contract, env/secret shape) and M3's env contract if M3 landed first.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → `make generate manifests` when CRD types change → validate tests pass → commit (comprehensive, functional message; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run `cd operator && make test-unit` locally; KIND available — run a 1-3 resource check locally before relying on CI; prefer the full e2e in CI. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all prior phases + this work) posted as a PR comment (not committed). Copy this plan to `plan/M4-memory-store-crd.md` and write `impl/progress/M4-*.md` + `impl/learnings/M4-*.md`.

## Problem statement

Add the declarative control plane that deploys and operates the M2 memory service: a `MemoryStore` CRD carrying **only infrastructure and models** (no behavioural knobs), an operator controller that reconciles it into the memory-service `Deployment` and `Service` (plus a `PersistentVolumeClaim` in `local` mode), wiring the storage secret and the referenced `ModelAPI` endpoints as environment, validating that model references resolve and are Ready, and reporting health and the service endpoint in status. The inline working-only `MemoryConfig` on the Agent is replaced with a **slim behavioural block** (`storeRef`, `shortTermTokenBudget`, `rollingSummary`, `recall.presentation`, `failureMode`) surfaced to the runtime as the new `MEMORY_*` env (the `scope` selector lands in M5). CRD manifests, deepcopy, RBAC, the memory-service image default, and the Helm chart are regenerated and wired.

## Current-state grounding (researched)

- **Workload-deploying template (MCPServer).** `operator/controllers/mcpserver_controller.go:47-260` is the reconcile shape to copy: fetch CR → finalizer → init status `Pending/Ready=false` → `Deployment` create/update (`:115-172`) → `Service` create/update (`:174-198`) → status endpoint (`:200-202`) → copy deployment status + readiness (`:244-258`). `constructDeployment` (`:266-326`) sets labels, replicas, container, owner refs via `controllerutil.SetControllerReference` (`:130-133`, `:182-185`), and a pod-spec hash annotation for rollouts. RBAC markers at `:55-60`. Status type `MCPServerStatus` with `phase` enum `Pending|Ready|Failed` (`mcpserver_types.go:48-69`).
- **Mode-enum + config-block pattern (ModelAPI).** `operator/api/v1alpha1/modelapi_types.go:8-128`: `ModelAPIMode` enum (`:8-16`), `ProxyConfig`/`HostedConfig` blocks, `spec.mode` enum marker (`:97-128`), `ModelAPIStatus` with `phase` (`:132-150`). `modelapi_controller.go:341-442` `constructDeployment` switches on mode; `PROXY_API_KEY` supports `value` or `valueFrom.secretKeyRef` (`:478-493`) — the secret pattern for `storage.external.connectionSecretRef`. This is exactly the shape for `storage.type: local|external` with `localConfig`/`externalConfig` blocks.
- **Agent ↔ ModelAPI reference + status.** `agent_types.go:193-200` `spec.modelAPI`/`spec.model` are name+id strings; `agent_controller.go:110-156` resolves the ModelAPI by name, waits on readiness, validates the model; `LinkedResources["modelapi"]` (`:357-360`). `MemoryStore.models.{summarization,embedding}` each `{modelAPI, model}` resolve the same way.
- **Agent memory env wiring (to be redesigned).** `agent_controller.go:599-633` sets `MEMORY_ENABLED|TYPE|REDIS_URL|CONTEXT_LIMIT|MAX_SESSIONS|MAX_SESSION_EVENTS`; the inline CRD block is `MemoryConfig` at `agent_types.go:51-79` (`enabled/type/contextLimit/maxSessions/maxSessionEvents`). M4 replaces both with the slim block and the new env M3 reads.
- **Chart/codegen.** `operator/Makefile:54-81`: `make generate` (deepcopy), `make manifests` (CRDs to `config/crd/bases`), `make helm` (kustomize→helmify, CRDs moved to `chart/crds/`). `defaultImages` in `operator/chart/values.yaml:31-41`; images surfaced via `operator/chart/templates/operator-configmap.yaml:11-18`; RBAC in `operator/chart/templates/kaos-operator-rbac.yaml`.

## Design plan (how it fits)

- **CRD types.** Add `operator/api/v1alpha1/memorystore_types.go`: `MemoryStoreSpec{ engine (enum mem0), storage{ type (enum local|external), local{ provider (enum chroma), persistentVolume{ size } }, external{ provider (enum pgvector), connectionSecretRef{ name, key } } }, replicas, models{ summarization{ modelAPI, model }, embedding{ modelAPI, model } }, extraction{ concurrency } }` and `MemoryStoreStatus{ phase (Pending|Ready|Failed), ready, endpoint, message, deployment }`, mirroring `ModelAPI`'s markers (shortNames, printcolumns Engine/Storage/Ready/Phase, `subresource:status`). Validation: `local` requires `local`, `external` requires `external` + `connectionSecretRef`; `replicas==1` enforced for `local`.
- **Controller.** Add `operator/controllers/memorystore_controller.go` modelled on the MCPServer controller: fetch → finalizer → init status → resolve+validate `models.{summarization,embedding}` ModelAPIs (by name, ready-gated, like `agent_controller.go:110-156`) → construct `Deployment` (memory-service image from `DEFAULT_MEMORY_SERVICE_IMAGE`, env from storage config + resolved ModelAPI endpoints + `extraction.concurrency`, secret via `valueFrom.secretKeyRef` for `external` DSN) → `Service` → `PersistentVolumeClaim` for `local` → owner refs on all → readiness from the service `/readyz` reflected into status endpoint/phase. RBAC markers for `memorystores`, `persistentvolumeclaims`, plus existing `deployments`/`services`/`configmaps`.
- **Slim Agent block.** Replace `MemoryConfig` (`agent_types.go:51-79`) with `MemoryConfig{ storeRef, shortTermTokenBudget, rollingSummary, recall{ presentation: block|tools|both }, failureMode: soft|strict, enabled }` (the `scope` selector is added in M5). Update `agent_controller.go` to resolve `storeRef` to a `MemoryStore` endpoint, gate readiness on the store being Ready (per [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md): store unavailable → Agent not-Ready but still serving working-only), and set the new `MEMORY_*` env M3 consumes (`MEMORY_STORE_ENDPOINT`, `MEMORY_SHORT_TERM_TOKEN_BUDGET`, `MEMORY_ROLLING_SUMMARY`, `MEMORY_RECALL_PRESENTATION`, `MEMORY_FAILURE_MODE`, `MEMORY_ENABLED`), removing the old keys.
- **Chart/images.** Add `defaultImages.memoryService` to `values.yaml`, emit `DEFAULT_MEMORY_SERVICE_IMAGE` in `operator-configmap.yaml`, add the `MemoryStore` CRD to `chart/crds/`, and the controller RBAC to `kaos-operator-rbac.yaml`. Register the controller in `main.go`/`SetupWithManager` and the scheme.

## Numbered TODOs

1. **CRD types + codegen.** Add `memorystore_types.go` with the spec/status above and kubebuilder markers; register in the scheme. Run `make generate manifests` and `make helm`. **Validate**: `cd operator && make generate manifests` produces the CRD + deepcopy with no diff drift; `go build ./...`; the CRD validation (local-required-for-local etc.) is expressed as markers/`CEL` where possible.

2. **MemoryStore controller (deploy service).** Add `memorystore_controller.go` modelled on the MCPServer controller: reconcile → init status → construct `Deployment`+`Service`(+`PVC` for `local`) for the memory-service image with env from storage/models/extraction, owner refs, pod hash annotation; readiness from the service. Register in `main.go`. **Validate**: envtest unit test — a `local` `MemoryStore` produces a Deployment/Service/PVC with the right image, env, and owner refs, and reaches Ready when the deployment is available; `make test-unit`.

3. **Model reference resolution + secret wiring.** Resolve `models.summarization`/`models.embedding` to their `ModelAPI` endpoints (name lookup, ready-gated, validate the model), inject them as env, and wire `storage.external.connectionSecretRef` via `valueFrom.secretKeyRef`. **Validate**: envtest — unresolved/not-ready ModelAPI holds the store `Pending` with a clear condition; external DSN is mounted from the secret; `make test-unit`.

4. **Slim Agent memory block + env redesign.** Replace `MemoryConfig` with the slim behavioural block; update `agent_controller.go` to resolve `storeRef`, gate readiness on store-Ready (not-Ready-but-serving when down), and set the new `MEMORY_*` env; remove the old keys and the `local|redis` type. Run `make generate manifests`. **Validate**: envtest — an Agent with `storeRef` gets the new env and the store link in status; store-down yields not-Ready with the documented condition while the agent still deploys; `make test-unit`.

5. **Chart, RBAC, defaultImages.** Add `defaultImages.memoryService` (`values.yaml`), emit `DEFAULT_MEMORY_SERVICE_IMAGE` (`operator-configmap.yaml`), add the `MemoryStore` CRD to `chart/crds/`, add controller RBAC (`memorystores`, `persistentvolumeclaims`, status/finalizers) to `kaos-operator-rbac.yaml`. **Validate**: `make helm`; `helm template operator/chart` renders the CRD, the new image env, and the RBAC; `helm lint operator/chart`.

6. **E2E + PR.** Add `operator/tests/e2e/test_memory_store_e2e.py` (modelled on `test_modelapi_e2e.py`): apply a `MemoryStore` (local mode) + a `ModelAPI`, wait for the memory-service Deployment Ready, apply a memory-enabled Agent, confirm it reaches Ready and its runtime env points at the store; tear down. Reuse `conftest.py` helpers; suppress to `./tmp/null`. **Validate**: the e2e passes on local KIND; dispatch the e2e workflow on the branch and confirm green. Write `impl/progress/M4-*.md` + `impl/learnings/M4-*.md`, copy this plan, push `feat/memory-store-crd`, open the stacked PR, confirm CI green, write the gitignored `REPORT.md` (M0–M4) and post it as a PR comment.

## Validation per task

- Per-TODO: `cd operator && make generate manifests && make test-unit`; `helm template`/`helm lint` for chart changes. The operator unit suite (envtest) and e2e run in KAOS CI.
- The memory e2e is KIND-based; run a minimal local check first, then the full suite via `workflow_dispatch --ref feat/memory-store-crd`.

## Commit / PR strategy

- `feat/memory-store-crd` stacked off `feat/memory-service` (rebase onto M3's tip if M3 lands first); one comprehensive commit per TODO; Copilot co-author trailer; CI green. `REPORT.md` gitignored, posted as a PR comment.
- Keep the `MEMORY_*` env contract matched with M3.

## Out of scope (later phases)

The runtime client itself (M3); the `scope` selector field and non-optional fail-closed enforcement, A2A inheritance, and erasure fan-out (M5 — M4 ships the infra/behaviour split and store-Ready gating only); CLI install integration and samples (M6 — M4 makes the chart installable, M6 adds the `--memory-enabled` switch and dev Postgres); HA tuning, metrics, durable-queue decision, versioned schema migration tooling, docs (M7).
