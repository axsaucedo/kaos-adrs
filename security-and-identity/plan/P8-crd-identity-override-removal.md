# CRD identity override (`spec.security.id`) removal — implementation plan

**Branches (KAOS)**: surgical rewrite of the existing stack — drop `feat/crd-identity-override` (PR #238), edit `feat/sync-service-productionisation` (PR #240), rebase `feat/sdk-token-lifecycle` (#239), `feat/network-policy-and-tls` (#241), `feat/enforcement-and-hardening` (#242).
**Supersedes**: `P8-crd-identity-override.md` and the `spec.security.id` decision in ADR-KAOS-001.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change -> validate tests pass -> commit (comprehensive, functional message describing WHAT changed; NO phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Push to the PR and validate CI green. Run Go/python tests locally; KIND available — run 1-3 checks locally before relying on CI; prefer the full suite in CI. Be efficient with testing. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null` (create it if missing). Do NOT use `/tmp`.
- End: gitignored `REPORT.md`, posted as a PR comment (not committed). Copy this plan here, and update `impl/progress` + `impl/learnings` entries.

## Problem statement

`spec.security.id` lets Agent/MCPServer/ModelAPI override their logical identity from the namespace-scoped default (`kaos://{kind}/{namespace}/{name}`) to a namespace-independent `kaos://{kind}/{id}`. Because an explicit id is shared by construction, it requires collision/adoption resolution (oldest-creationTimestamp wins) implemented **twice** — once in the operator (`pkg/identity/conflict.go` plus a gate in all three controllers) and once in the Go sync projection (`winnersAndConflicts`/`IdentityConflict`). The two copies must agree byte-for-byte or the operator and sync diverge on who owns an identity, which is a fragile correctness coupling on a security-sensitive path. The feature's only benefit is identity continuity across a namespace move or rename, which is speculative for current alpha usage; and the design forbids concurrent shared identity anyway (a duplicate marks the younger resource Failed), so it does not even serve the most plausible future "shared identity" use case. We remove the feature entirely: logical identity becomes **always** `kaos://{kind}/{namespace}/{name}`, which is unique by construction, so every collision/winner code path disappears on both planes. The future "single identity / multiple instances" question is deferred and documented, not implemented.

## Strategy: surgical stack rewrite

The feature is introduced wholesale by the dedicated PR #238 (`feat/crd-identity-override`) and consumed above it. Of the five PRs above its parent, only two carry the identity-override logic in their own diff; the other three merely sit on top.

- **Drop #238 from the stack.** `git rebase --onto feat/extproc-token-exchange feat/crd-identity-override feat/sdk-token-lifecycle` replays #239 onward onto #237, skipping #238. Because #238's entire diff is the feature — CRD `SecuritySpec` and the `Security` field on all three kinds, `pkg/identity/{identity,conflict}.go` plus tests, the three controller conflict gates, the `AGENT_AUTH_IDENTITY` resolution, regenerated CRD/deepcopy/Helm manifests, the `7-stable-identity.yaml` sample and its kustomization entry, the CRD docs, and a CLI test tweak — dropping it auto-removes that whole surface.
- **Edit #240 (`feat/sync-service-productionisation`).** The Go sync rewrite authored `projection.go`/`reconciler.go` to consume `security.id`. Amend those commits so the Go sync never reads `spec.security.id` and has no `winnersAndConflicts`, `IdentityConflict`, or conflict logging; collapse `logicalPath`/`ResolveLogicalID` to namespace/name; trim the related `projection_test.go` cases. This is the "avoid the collision detection in the sync service" simplification.
- **Rebase #239 / #241 / #242.** Their controller hunks are unrelated to identity (actor-token mount, NetworkPolicy creation, enforcement tweak); they need only mechanical rebasing, with textual conflict resolution where a hunk's context abuts a removed conflict-gate block.
- **#238 left open** (not closed) per instruction; it is dropped from the merge lineage and becomes an isolated, unmerged PR. This is a risk: if ever merged it re-adds the feature. Flagged prominently in REPORT.md.

The `AGENT_AUTH_IDENTITY` env stays (the data plane consumes it) but always resolves to `kaos://agent/{namespace}/{name}`. A slimmed `pkg/identity` keeping only `Resolve(kind, namespace, name)` is retained as the single operator-side identity-format source of truth; `conflict.go` and the override branch are removed. The sync projection keeps producing the identical `external_id` so the operator and sync stay in agreement on every resource's identity.

## Current-state grounding (researched)

- `spec.security.id` is **not on `main`**. It is introduced by commit `50e88fd1` on `feat/crd-identity-override` (#238) and present in every branch stacked above it.
- The consumer surface at the stack tip (#242): operator CRD (`api/v1alpha1/security_types.go` with `SecuritySpec{ID}`/`GetID`, the `Security *SecuritySpec` field on `agent_types.go`/`mcpserver_types.go`/`modelapi_types.go`, `zz_generated.deepcopy.go`, generated `config/crd/bases/*` and `chart/crds/*`); operator identity package (`pkg/identity/{identity,conflict,identity_test,conflict_test}.go`); operator controllers (the conflict gate in `agent_controller.go` ~98-140, `mcpserver_controller.go`, `modelapi_controller.go`; the `AGENT_AUTH_IDENTITY` injection at `agent_controller.go:835-836` via `identity.Resolve(identity.KindAgent, ns, name, agent.Spec.Security.GetID())`; tests `agent_conflict_test.go`, `agent_auth_env_test.go`); operator samples (`config/samples/7-stable-identity.yaml` plus its `kustomization.yaml` entry); the Go sync (`internal/projection/projection.go` SecurityID threading plus `winnersAndConflicts`/`IdentityConflict`/`logicalPath`, `internal/projection/projection_test.go`, `internal/sync/reconciler.go` `toResource` reading `spec.security.id` and conflict logging); `kaos-cli/tests/test_cli_integration.py`; in-repo docs `docs/operator/{agent,mcpserver,modelapi}-crd.md`.
- Per-PR ownership of the identity surface: #238 introduces all of it; #240 creates the Go sync consumer logic; #239/#241/#242 touch the same controller files but for unrelated reasons (no `identity`/`conflict`/`Resolve`/`security` references in their hunks).
- `operator/pkg/security/config.go` matches a substring grep but is gateway-security config, unrelated — verify and leave untouched.
- The current operator resolver (`pkg/identity/identity.go`) is `Resolve(kind, namespace, name, securityID)` returning `kaos://{kind}/{id}` when `securityID != ""` else `kaos://{kind}/{namespace}/{name}`. Removal collapses this to the namespace/name form only.

## Design plan (target state)

1. Logical identity is always `kaos://{kind}/{namespace}/{name}`; no per-resource security knob remains. `SecuritySpec` is removed entirely and `spec.security` disappears from all three CRDs.
2. The operator and the sync service each keep one canonical identity-format definition producing the same string; neither has conflict, winner, or adoption logic.
3. Behaviour is otherwise unchanged: per-agent credential Secret mint/mount/auth, gateway ext_authz, and ext_proc token exchange all operate on the default identity, which was already the common path. The per-agent Secret naming stays coordinate-based (`<prefix>-<agent name>`) and is unaffected.
4. Deferred design note (recorded in ADR-KAOS-001): a future shared-identity capability — one logical identity intentionally shared across multiple instances or namespaces — is out of scope; if introduced it must be designed to PERMIT concurrent holders, since the removed oldest-wins model would actively fight that use case and would have to be redesigned regardless. Removing now therefore burns no useful future foundation.

## TODOs

1. **Prove the target end-state on a scratch branch.** Off the stack tip (#242), delete the full surface (operator types, identity package, controller gates, samples, regenerated manifests, the Go sync consumer logic, and the in-repo docs), regenerate, and validate: operator builds, `make manifests` produces no diff, operator unit tests pass, `go test ./...` passes in `sync-service`, and `kaos-cli` tests pass. Throwaway branch to de-risk the rewrite; not kept.
2. **Drop #238 from the stack.** `git rebase --onto feat/extproc-token-exchange feat/crd-identity-override feat/sdk-token-lifecycle`; resolve the controller textual conflicts introduced by #239/#241/#242. Validate the rebased tip: operator builds, `make manifests` clean, operator unit tests pass.
3. **Strip the Go sync consumer logic on #240.** Interactive-rebase amend the projection/reconciler commits so the Go sync never reads `spec.security.id` and has no `winnersAndConflicts`/`IdentityConflict`/conflict logging; collapse identity resolution to namespace/name; update `projection_test.go`. Validate `go test ./...` at the amended commit and again at the rebased tip.
4. **Regenerate and verify the operator is clean.** `make generate manifests`; grep the tree for `security.id`/`SecuritySpec`/`pkg/identity`/`DetectConflict`/`AGENT_AUTH` and confirm only the intended `AGENT_AUTH_IDENTITY` (namespace/name) injection remains; operator unit tests plus lint.
5. **Verify in-repo docs and CLI.** Confirm `docs/operator/*-crd.md` have no `security.id` (auto-dropped with #238) and still read correctly; confirm `kaos-cli` tests pass without #238's tweak; remove any lingering reference to the dropped sample.
6. **Update the docs repo.** Amend ADR-KAOS-001 to record the removal (identity always namespace/name) and the deferred shared-identity design note; update P8 plan/progress/learnings and the P10 learnings carry-forward bullet to reflect the removal; note it in `proposed-split.md`. Committed in this repo separately from the KAOS changes.
7. **Local KIND validation (1-3 e2e).** Reuse the running cluster; run a small slice of the AIB+sync and enforcement e2e to confirm default-identity mint/mount/auth still works before pushing.
8. **Push rebased branches and run per-branch CI.** Force-push #239/#240/#241/#242 (and any top validation branch); dispatch the Go/Python/E2E workflows per branch (switch to the `axsaucedo` gh account for dispatch, then switch back); confirm green.
9. **Genuine manual e2e per the runbooks.** Using `impl/runbooks/security-enforcement-e2e.md` and `impl/learnings/manual-e2e-P6-P10-validation.md`: verify the per-agent Secret is created and mounted, the agent authenticates, the gateway ext_authz allows/denies on the namespace/name identity, ext_proc performs on-behalf-of token exchange, and the default (formerly "no-identity") path works end-to-end. Record outcomes for the P10/P12 learnings.
10. **REPORT.md and PR comment.** Write `REPORT.md` (do not commit) and post it on the top PR. Include the #238-left-open risk note.

## Validation per TODO

Operator: `cd operator && make generate manifests && make test-unit` (plus `make lint` where present). Sync: `cd sync-service && go test ./...`. CLI: `cd kaos-cli && source .venv/bin/activate && python -m pytest tests/ -v`. E2E: prefer CI per branch; run 1-3 locally on KIND first. Scratch in `./tmp`, suppressed output to `./tmp/null`.

## Commit / PR / CI strategy

Realised through stack rewrite, not add-on commits: dropping #238 removes its commit; #240's commits are amended to a clean state; #239/#241/#242 are rebased. Any net-new edit uses comprehensive conventional commits describing exactly what changed — no phase/task/ADR references in messages, branches, or comments — with the Copilot co-author trailer. Force-push all rewritten branches and validate each branch's CI. Author email stays `alejandro.saucedo@zalando.de`.

## Notes / risks

- #238 left open per instruction — a dangling PR that re-adds the feature if merged; call it out prominently.
- The stack rewrite force-pushes five refs; textual conflicts are expected in the three controllers.
- ADR-KAOS-001 is an Accepted decision being reversed; the amendment must be explicit and self-contained.
- Operator/sync identity-string parity must be preserved (both always `kaos://{kind}/{namespace}/{name}`).
