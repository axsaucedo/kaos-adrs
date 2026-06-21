# End-to-end wiring and install — implementation plan

**Branch (KAOS)**: `feat/aib-install-and-sync`, stacked off `feat/gateway-ext-authz`; PR targets `feat/gateway-ext-authz`.
**Branch (AIB, local-only, not pushed)**: continue `feat/aib-deployability-foundation` (the stacked base under `feat/aib-access-check`).
**Docs (kaos-ai-docs)**: new `adr-aib/ADR-AIB-000-*`, `plan/P3-*.md`, `impl/progress` + `impl/learnings` entries.
**Tracking issue**: axsaucedo/kaos#231.

## Problem

P0 (feasibility), P1 (Python propagation SDK, PR #232) and P2 (gateway `ext_authz` enforcement, PR #233) are done. We now install and wire the components into a real cluster and prove the end-to-end MVP: a one-command(-ish) install yields a cluster where an agent->MCP call is **propagated** (P1) and **authorized** (P2) end-to-end, backed by **actually-installed** AIB + a KAOS->AIB sync service.

## Decisions (confirmed)

- **Sync service language: Python.** A working `tmp/security/sync/sync.py` prototype already projects LocalClients / synthetic services / PermissionSets / per-agent credentials against the AIB admin API. Reusing it is the fastest path to the MVP; P5 hardens it and may reassess a Go rewrite for native watch/extraction.
- **Sync mechanism: periodic list-reconcile loop** (watch deferred to P5).
- **`--auth-enabled` scope (P3): AIB + sync + agent-auth wiring + credential mounting.** Keycloak / user-auth is deferred to P6; user auth is simulated/skipped here.
- **Credential mounting: Agent pods only.** The actor/caller is always an Agent; MCPServer-as-caller is a later follow-up.
- **Auth e2e venue: local KIND only.** `agentic-identity-broker` is gitignored and unpublished (no public image/chart), so the full auth path cannot run in KAOS GitHub Actions. KAOS CI runs the existing suites plus the new sync unit tests, operator unit/envtest, and CLI dry-run tests. The auth e2e is validated on the local KIND cluster and documented in `REPORT.md`.

## Current state by domain

- **AIB** (`agentic-identity-broker/`, gitignored in KAOS): foundation branch `feat/aib-deployability-foundation` carries the public-alpine-base and chart-schema fixes; access-check branch stacks the decision service + HTTP + gRPC `ext_authz` surfaces. Chart is `charts/agentic-identity-broker`. Admin API: agents, services, permission-sets, agent client-credentials (create/get/revoke). `client_credentials` mint already works for LocalClients; `storage.type=memory` installs with no Postgres. ADR-AIB-000 is referenced by the plan but **does not exist yet**.
- **Sync prototype**: `tmp/security/sync/sync.py` (+ `40-sync.sh`, `sample-kaos.yaml`) — idempotent projection: MCPServer->service `kaos-mcpserver-<ns>-<name>`, edge->PermissionSet `kaos:mcpserver:<ns>:<mcp>:call`, Agent->LocalClient (no `client_id`) bound to those sets, then `POST /agents/{id}/client-credentials`. Reads `kubectl get agents,mcpservers -o json`.
- **Operator**: `pkg/security` has `ExtAuthzURL` config + `SecurityPolicy` generation (P2). `constructDeployment` (agent_controller.go) builds the agent pod and already supports podSpec/container overrides -> the credential-mount insertion point. No credential mounting or per-agent secret convention yet.
- **CLI**: `kaos-cli/kaos_cli/install.py` `install_command` with `_install_gateway_api` / `_install_metallb` / `_install_redis` helpers and a final `helm upgrade --install` of the operator chart with `--set` wiring; flags declared in `system/__init__.py`. No `--auth-enabled` yet. Dry-run/YAML-validation tests under `kaos-cli/tests/`.
- **ADRs**: ADR-KAOS-008 (integration/sync: external AIB lifecycle, CLI-owned integration, lightweight external sync service, per-agent credential Secrets named by `credentialSecretPrefix`, CLI-installed packaging), ADR-KAOS-009 (`security.agentAuth.extAuthzUrl`, credential mounting, fail-closed), ADR-KAOS-001 (`external_id`, LocalClient rule), P0 learnings (LocalClient design, deployability groundwork).

## Design plan

Bottom-up: finish the AIB foundation, build and unit-test the sync **projection** as a pure library, wrap it in a runtime that writes credential Secrets, teach the operator to mount those Secrets, package the sync chart, add the CLI `--auth-enabled` convenience, then prove the whole thing end-to-end on local KIND.

- **Sync service** lives in the KAOS repo at `sync-service/` (Python package + `Dockerfile` + `chart/`), CLI-deployed (ADR-KAOS-008 "now — same repo" packaging). Projection logic is a tested library; the runtime is a periodic reconcile loop using the `kubernetes` client (in-cluster config) + `httpx` to the AIB admin API (preauth `X-Remote-User` header, admin URL/creds from its own config). It writes per-agent `client_id`/`client_secret` into Secrets `kaos-aib-<agentid>`.
- **Operator** gains a `CredentialSecretPrefix` in `pkg/security` config and, when security is operational, mounts the per-agent Secret into the agent pod as env (`AIB_CLIENT_ID`/`AIB_CLIENT_SECRET` via `secretKeyRef`, optional so the pod can start) plus the AIB token-endpoint env the SDK uses. Gated and default-off; envtest stays green because security is off by default.
- **CLI `--auth-enabled`**: `_install_aib` (AIB chart, `storage.type=memory`, generated JWE/encryption/preauth keys, dev image build+`kind load` when unpublished) -> `_deploy_sync_service` (render sync chart with AIB admin URL + watch scope) -> wire `security.agentAuth.extAuthzUrl` and `security.agentAuth.credentialSecretPrefix` into the operator `helm` args. Idempotent; mirrors the existing helper pattern.
- **AIB foundation (ADR-AIB-000)**: chart defaults to `memory`; a committed dev values preset wires JWE/encryption/preauth; a repeatable image build (stub consent UI) + `kind load`; documented so the CLI dev-install path is reproducible. Commits land on the AIB foundation branch; ADR-AIB-000 is written in kaos-ai-docs.

### Out of scope (later phases)

NetworkPolicy / ClusterIP bypass prevention and Gateway TLS (P4); Keycloak/user-auth + gateway `jwt_authn` (P6); `ext_proc` token exchange (P7); `spec.security.id` CRD override (P8); sync watch + productionisation + extraction (P5/P10); upstreaming AIB from a fork (P14).

## TODOs

1. **AIB deployability foundation + ADR-AIB-000.** On `feat/aib-deployability-foundation`: make the AIB chart install cleanly with `storage.type=memory` by default and a committed dev values preset wiring JWE/encryption-key + admin/enduser preauth; add a repeatable image-build path (stub consent UI) + `kind load` recipe. Author `ADR-AIB-000` in kaos-ai-docs documenting the foundation (image/chart/memory-default/keys). **Validate**: `helm template` + `helm install` of the AIB chart on local KIND comes up healthy on memory backend; AIB `just check` + `just test` green.
2. **Sync projection library + unit tests.** Create `sync-service/` Python package; port `sync.py` into a tested projection module (KAOS Agent/MCPServer[/ModelAPI] -> desired AIB records: LocalClient agents, synthetic services, PermissionSets, requested edges) with idempotent create-or-get. **Validate**: unit tests (projection shape, naming convention, idempotency, no-edge skip) green via `pytest`; `make lint`/black.
3. **Sync runtime + credential Secrets + image.** Add the periodic reconcile loop (kubernetes client in-cluster config + `httpx` AIB admin client with preauth header), generate per-agent client-credentials and write/refresh `kaos-aib-<agentid>` Secrets; basic drift/status logging; `Dockerfile`. **Validate**: unit tests for the reconcile/secret-shaping with a mocked AIB admin + fake k8s client; image builds; a local run against KIND projects `tmp/security/sync/sample-kaos.yaml` and the access-check honors edges (github allowed, slack denied) — reuse `40-sync.sh` logic into a repeatable check.
4. **Operator credential mounting.** Add `CredentialSecretPrefix` to `pkg/security` config (env + Helm value under `security.agentAuth`); when security is operational, mount the per-agent AIB credential Secret into the agent pod (optional `secretKeyRef` env `AIB_CLIENT_ID`/`AIB_CLIENT_SECRET`) and set the AIB token-endpoint env. **Validate**: `pkg/security` unit tests + a controller/envtest asserting env is injected when configured and absent when off; `go test ./...`; `helm template` both modes.
5. **Sync service Helm chart.** Minimal chart/manifests for the sync Deployment: ServiceAccount + RBAC (list/watch agents,mcpservers,modelapis; create/update secrets), AIB admin URL/credential config, image ref. **Validate**: `helm template` renders; `helm install` on KIND brings the sync pod up and reconciles the sample resources; manifests lint.
6. **CLI `kaos system install --auth-enabled`.** Add the flag (`system/__init__.py`) + `_install_aib` + `_deploy_sync_service` helpers and wire `security.agentAuth.extAuthzUrl` + `security.agentAuth.credentialSecretPrefix` into the operator `helm` args (`install.py`); reuse the build/`kind load` dev path for the unpublished AIB image. **Validate**: CLI dry-run/YAML-validation tests (existing pattern) cover the new wiring; `pytest` for kaos-cli green.
7. **End-to-end local KIND validation + docs + PR/REPORT.** On the local KIND cluster, run the `--auth-enabled` install path, deploy a sample Agent->MCPServer with a requested edge, and verify end-to-end: P1 two-identity propagation across the hop **and** P2 `ext_authz` allow (granted edge) / deny (ungranted) through the gateway, with real installed AIB + sync. Write `impl/progress` + `impl/learnings` (P3) and copy this plan to `kaos-ai-docs/.../plan/P3-aib-install-and-sync.md`. Push `feat/aib-install-and-sync`, open the stacked PR into `feat/gateway-ext-authz`, dispatch `go-tests`/`python-tests`/`e2e` on the branch, write the gitignored `REPORT.md` (all phases P0–P3 + this turn) and post it as a PR comment.

## Validation & CI strategy

- Per-TODO: run the targeted unit/lint locally before committing (AIB `just test`; operator `go test ./...` + `make manifests`; kaos-cli `pytest`; sync `pytest`+black).
- Local KIND (`kind-kaos-e2e`) is the venue for the auth e2e (T3, T7) — you have it running; reuse the `tmp/security/` harness and suppress output to `tmp/null`.
- Push the stacked PR and dispatch `go-tests.yaml` / `python-tests.yaml` / `e2e-tests.yaml` via `workflow_dispatch --ref feat/aib-install-and-sync` (stacked PRs don't auto-trigger into a non-main base). The existing e2e suite runs with security default-off and must stay green; the auth e2e is local-only and documented.
- Push under the `axsaucedo` gh account (EMU `alejandro-saucedo_zse` can't push/comment on the personal repo); **keep the commit author as the repo default** `alejandro.saucedo@zalando.de` — do NOT override author email when switching gh accounts. Restore the EMU account after.

## Commit / PR conventions

- Conventional, functional commit messages; **no phase/task/ADR references** in commit messages, branches, code comments, or the PR description — describe the work itself. Include the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits (kaos-ai-docs commits follow that repo's no-trailer convention).
- One commit per TODO. AIB-side commits stay on the local foundation branch (never pushed).

## REPORT.md

At the end, overwrite the gitignored `REPORT.md` with all tasks (P0–P3 + this turn), status, commits, local validation, CI status, and risks/follow-ups (AIB unpublished -> local-only auth e2e; sync Python-now/Go-later; credential mounting agents-only; Keycloak/TLS/NetworkPolicy deferred). Post it as a PR comment; never commit it.
