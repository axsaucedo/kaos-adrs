# P13 — Coarse authorization via OPA-in-ext_proc: architecture and enforcement core — implementation plan

**Repo / branch (KAOS)**: a feature branch stacked on the PR #260 lineage in the KAOS worktree (exact name chosen at execution; no phase/ADR reference in the branch name).
**Realises**: [ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md), [ADR 0002](../adrs/adr_0002_identity-and-authentication.md), [ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md).
**Build target**: AIB `main` (includes #222, OPA-in-ext_proc) plus AIB PR #397 (deployability), rebased and mergeable.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message describing WHAT changed; NO phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits. Commit author stays the repo default.
- Push to the PR and validate CI green. Run Go/python tests locally; KIND available — run 1–3 checks locally before relying on CI; prefer the full suite in CI. Be efficient with testing. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null` (create it if missing). Do NOT use `/tmp`.
- End: gitignored `REPORT.md`, posted as a PR comment (not committed). Update `impl/progress/` + `impl/learnings/` entries in the docs repo.

## Problem statement

The implemented stack (P0–P12) enforced authorization through a standalone AIB ext_authz access-check service behind a gateway `SecurityPolicy`, alongside a separate ext_proc token-exchange filter, and projected identity/permissions through a **standalone sync-service** (own Go module and deployable) that also mints and writes the per-agent credential Secret the operator only mounts. AIB `main` now embeds OPA inside the ext_proc filter (#222), so one gateway hook does token-exchange and authorization together. This phase re-bases KAOS on that topology — OPA-in-ext_proc as the single decision point for both authorization models — and folds the sync-service into the operator, removing a whole deployable and the credential-Secret split-brain. It delivers the enforcement **core** (Model 1 data path, identity/verification, enforcement posture); the source-of-truth/override modes and framework enablement follow in [P14](./P14-authorization-modes-and-enablement.md).

## Current-state grounding (verified)

- **Sync-service** (`sync-service/`, separate `go.mod`): controller-runtime manager (`cmd/main.go`, Settings via envconfig) with a single whole-world sentinel reconciler (`internal/sync/reconciler.go`); pure projection `internal/projection/projection.go` — `Project(resources) → DesiredState` building Services, PermissionSets, and Agents keyed by logical ids `kaos://<slug>/<ns>/<name>`, with AIB-shaped `AdminBody()` serialisation hung off the DesiredState types; AIB admin client `internal/aib/client.go` (`MintCredentials` via `POST /agents/{id}/client-credentials`, plus service/permission-set/agent upserts and prune). It MINTS and WRITES the per-agent credential Secret. PR #260 adds agent→agent access-edge projection to this code.
- **Operator** (`operator/`, separate `go.mod`): single controller-runtime manager registering the Agent, MCPServer, ModelAPI controllers (`main.go`). It only MOUNTS the credential Secret (`pkg/security/config.go`, mount dir `/var/run/aib`); it does not mint it. The `kaos-aib-<name>` Secret naming convention is duplicated across the operator and the sync-service (split-brain).
- **Security config** (`operator/pkg/security/config.go`): `Issuer` defaults to "the broker"; `TokenEndpoint()` = `<issuer>/oauth2/token`; `AgentJWKS()` = `<issuer>/oauth2/jwks.json`; `IsOperational() == (ExtAuthzURL != "")` and **also** gates `CredentialMountingEnabled` and `NetworkPolicyEnabled`. Controllers gate on `IsOperational() || ExtProcEnabled()`. `securitypolicy.go` renders the JWT authn block only when an issuer is set.
- **Runtime SDK** (`pydantic-ai-server/aib/identity.py`): mints the actor token via `client_credentials`; provider-agnostic (`AGENT_AUTH_TOKEN_ENDPOINT`/`ISSUER`); `sub` = logical identity = `AGENT_AUTH_IDENTITY`. `instrument.py` injects the `authorization` (subject) and `x-agent-authorization` (actor) headers.
- **AIB #222** (`internal/extproc/authorization/authorizer.go`): `policy.path` compiles once and is **static** (data change needs an ext_proc restart); `policy.config_file` runs OPA SDK bundle mode with background-poll **hot-reload** (fail-closed until first bundle). Mutually exclusive. `server.go` only invokes OPA when a subject bearer is present (the **G1 gap**). The experiment rego uses `io.jwt.decode` (no signature verification) as an explicit shortcut; nothing in ext_proc validates the actor header today.

## Design plan (target state)

1. One enforcement point: OPA embedded in AIB ext_proc, invoked via the ext_proc `EnvoyExtensionPolicy` KAOS already renders, for both models; ext_authz `SecurityPolicy` generation becomes an optional, default-off generic seam (no longer assuming AIB #398). See [ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md).
2. The operator is the single owner of identity projection and the credential Secret: an isolated `AIBProjectionReconciler` (whole-world sentinel) is the sole AIB caller, ConfigMap writer, and credential minter; the workload reconciler never calls AIB. Credential Secrets get `ownerReference: Secret → Agent` for GC. See [ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md).
3. `Project() → DesiredState` becomes model-agnostic; the AIB admin serialisation moves into a Model-2 adapter (the only bespoke integration); Model 1 renders the same graph to a `data.kaos.grants` ConfigMap.
4. Actor-token verification is config-gated: a static generic rego branches `io.jwt.decode_verify` (when `data.kaos.jwks` is injected) vs `io.jwt.decode` (demo). See [ADR 0002](../adrs/adr_0002_identity-and-authentication.md).
5. "Security enabled" is decoupled from `ExtAuthzURL` so credentials and NetworkPolicy stay on independently.

## TODOs

1. **Security-config foundation.** In `operator/pkg/security/config.go`, introduce a broader `SecurityEnabled` predicate distinct from `ExtAuthzURL != ""`, and re-gate `CredentialMountingEnabled` and `NetworkPolicyEnabled` on it. Add typed config for authorization **model** (1 / 2 / both), **enforcement posture**, **verification mode**, and **populator mode** with simple safe defaults. Unit-test the predicate and parsing, including "ext_authz off but security on".
2. **Relocate the projection core into the operator.** Move `internal/projection` and `internal/aib` from `sync-service/` into the operator module; convert unstructured reads to typed CRD clients (Agent/MCPServer/ModelAPI). Keep `Project()` behaviour identical; port its unit tests. Validate `make test-unit`.
3. **Add the isolated projection controller.** Register an `AIBProjectionReconciler` (whole-world sentinel) as a second controller in the operator manager, with its own requeue/backoff; ensure the workload reconciler never calls AIB. Validate manager starts and both controllers register.
4. **Unify credential-Secret ownership.** Make the projection reconciler the sole minter/writer of the per-agent credential Secret with `ownerReference: Secret → Agent`; delete the bespoke prune-secrets path in favour of owner-reference GC; share one `kaos-aib-<name>` naming helper (remove the duplicate). Validate an Agent still gets its Secret; deleting the Agent GCs the Secret.
5. **Delete the standalone sync-service.** Remove the `sync-service/` deployable, its Helm chart/image, its CI job, and its `go.mod`. Confirm the chart renders without it and no dangling references remain.
6. **Model-agnostic projection core.** Strip AIB-specific `AdminBody()` serialisation off the `DesiredState` types into a Model-2 adapter package; keep `DesiredState` a pure grant graph keyed by the logical identities. Unit-test the pure core and the Model-2 adapter separately.
7. **Verify token `sub` == logical identity.** At runtime against a live broker, confirm the `client_credentials` token stamps `sub` as `kaos://agent/<ns>/<name>` (not an internal UUID). If UUID, key Model-1 data by UUID or carry a UUID→logical map. Record the finding in `impl/learnings/`.
8. **Model 1 emitter + static rego.** Ship a static generic rego asset (keys on actor identity + requested resource, checks `data.kaos.grants`, branches on `data.kaos.jwks` presence for `decode_verify` vs `decode`); render `DesiredState → data.json` and write it plus the rego into a ConfigMap; wire OPA `policy.path`/`policy.package`/`policy.decision` via the AIB #397 chart values so the ext_proc pod mounts and loads it. Unit-test the emitter; targeted KIND e2e that a mounted grant allows and a missing grant denies (demo mode).
9. **Config-gated JWKS injection.** Derive the IdP JWKS and inject `data.kaos.jwks` into the data ConfigMap only when an issuer is configured (verified mode); omit it in demo mode. Targeted e2e that verified mode rejects an unsigned/forged actor token while demo mode does not.
10. **Enforcement posture + ext_authz generalisation.** Make ext_proc OPA the default enforcement path under `SecurityEnabled`; generalise the ext_authz `SecurityPolicy` generation off the AIB-#398 assumption into an optional, default-off seam pointing at a configurable backend; keep the user-auth JWT authn, NetworkPolicy, and ext_proc `EnvoyExtensionPolicy` intact. Chart-render tests for default-off ext_authz; e2e enforcing via ext_proc OPA with no ext_authz.
11. **Local KIND validation (1–3 e2e)** on the running cluster before pushing: Agent gets a credential Secret, authenticates, and a Model-1 grant allows/denies via ext_proc OPA.
12. **Push, CI, REPORT.** Push the PR, dispatch Go/Python/E2E workflows (switch to the `axsaucedo` gh account for dispatch, then back), confirm green. Write `REPORT.md` (uncommitted) and post it as a PR comment; update `impl/progress/` + `impl/learnings/`.

## Validation per TODO

Operator: `cd operator && make generate manifests && make test-unit` (plus `go vet ./...`, `gofmt`). Python: `cd pydantic-ai-server && source .venv/bin/activate && python -m pytest tests/ -v && make lint` (only if runtime touched). E2E: prefer CI; run 1–3 locally on KIND first (port-forward the Envoy Gateway on macOS per the e2e instructions). Scratch in `./tmp`, suppressed output to `./tmp/null`.

## Commit / PR / CI strategy

One comprehensive conventional commit per TODO describing exactly what changed — no phase/task/ADR references in messages, branches, or comments — with the Copilot co-author trailer. Push to a single PR; validate each CI run green before the next TODO where practical. Fold-and-delete (TODOs 2–5) is a large refactor; run operator unit tests and a KIND smoke locally before pushing.

## Notes / risks

- The operator gains a dependency on the AIB admin API; contained by the isolated projection controller with its own backoff (broker outage stalls only projection, never workloads or health probes).
- Static `policy.path` restarts the ext_proc pod on Model-1 data changes; acceptable to start, bundle hot-reload is [followup F4](./followups.md).
- The G1 autonomous gap ([ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md)) means autonomous-only flows are unprotected in this version; user-present flows always enforce.
- Verify (do not assume) the broker's token `sub` before shipping the Model-1 key (TODO 7).
- Coarse granularity only; no MCP tool-level policy.
