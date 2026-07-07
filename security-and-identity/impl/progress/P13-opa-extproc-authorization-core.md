# P13 — Coarse authorization via OPA-in-ext_proc: architecture and enforcement core (progress)

**Phase**: P13 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P13-opa-extproc-authorization-core.md`](../../plan/P13-opa-extproc-authorization-core.md)
**Status**: In progress. Enforcement core, identity-projection fold, and the Model-1 data path are implemented and unit-validated; runtime broker verification and in-cluster enforcement e2e remain (need a live broker).
**Repos / branches**: KAOS `feat/opa-extproc-authorization` (PR #263, stacked on `docs/aib-222-opa-actor-verification` #260). AIB unchanged (targets `main` incl. #222 + #397).

## Outcome

P13 re-bases KAOS authorization on OPA embedded in the AIB ext_proc filter (#222) and folds the standalone sync-service into the operator, removing a whole deployable and the credential-Secret split-brain. It delivers the enforcement **core**: a single security predicate decoupled from ext_authz, one owner of identity projection and credential Secrets, a model-agnostic projection graph, the Model-1 KAOS-owned grant data path with a static actor-keyed policy, config-gated actor-token signature verification, and ext_proc OPA as the default enforcement path with ext_authz demoted to an optional, default-off seam.

## Scope delivered

- **Security-config foundation.** A `SecurityEnabled` predicate distinct from `ExtAuthzURL != ""` now gates credential mounting and NetworkPolicy so an ext_proc-only install keeps both on. Typed authorization config (model, enforcement mode, verification mode, populator mode) with safe defaults.
- **Projection folded into the operator.** `internal/projection` and `internal/aib` moved from the deleted sync-service into the operator module, converted to typed CRD clients; an isolated `AIBProjectionReconciler` (whole-world sentinel) is the operator's only broker caller and the sole minter/writer of per-agent credential Secrets, with `ownerReference: Secret → Agent` GC replacing the bespoke prune path and one shared naming helper. The standalone sync-service (deployable, chart, image, CI job, go.mod) is gone, with the chart/CLI/CI folded onto the operator.
- **Model-agnostic core.** `Project() → DesiredState` is a pure grant graph; the AIB admin serialisation lives in a Model-2 adapter (`internal/aib`), the only bespoke integration.
- **Model 1 data path.** A static `aib.extproc.authz` rego (keys on the actor identity from `x-agent-authorization` and the request's declared target resource, checks `data.kaos.grants`, branches on `data.kaos.jwks` presence for `decode_verify` vs `decode`); the operator renders `DesiredState → data.json` and writes it plus the policy into a ConfigMap gated on `AIB_AUTHZ_CONFIGMAP_NAME/NAMESPACE`.
- **Config-gated verification.** In verified mode (issuer configured) the operator fetches the IdP JWKS and injects it at `data.kaos.jwks` so the policy verifies the actor-token signature; demo mode omits it and decodes without verifying.
- **Enforcement posture.** ext_proc OPA is the default enforcement under `SecurityEnabled`; the ext_authz `SecurityPolicy` block is emitted only in `extauthz` enforcement mode with a configurable backend, while JWT authn is always emitted when an issuer is set and the SecurityPolicy is skipped entirely when neither applies. New `enforcementMode` chart knob.
- **Image build fix.** The operator image build copies the new `internal/` tree.

## Validation

- **Operator unit.** `go build ./...`, `go vet`, `gofmt` clean; `go test ./internal/... ./pkg/... ./controllers/`green (projection grant emitter, authz policy/data/JWKS emitters + fetch, config predicates incl. `ExtAuthzEnabled`/`AuthzJWKSURI`, SecurityPolicy default-off ext_authz + JWT-only, projection controller ConfigMap write/skip + verified-mode JWKS injection). Integration envtest suite is skipped locally (missing etcd binary — pre-existing env limitation).
- **Policy.** `opa check` clean; `opa eval` proves demo allow/deny and verified-mode forged-token rejection (validated in the `aib-222-verify` artifacts).
- **Chart.** `helm template` confirms default (ext_proc-only) emits no ext_authz/enforcement env and `extauthz` mode emits both `SECURITY_AUTHORIZATION_ENFORCEMENT` and the ext_authz URL. (No Go chart-render harness exists in-repo; verified by render.)
- **Image.** Operator image builds locally after the `internal/` COPY fix.
- **CI.** Go Tests and Python Tests green on `feat/opa-extproc-authorization`; E2E dispatched after the image-build fix.

## Follow-ups

- **Runtime broker verification (TODO 7).** Confirm the `client_credentials` token stamps `sub` as `kaos://agent/<ns>/<name>` (not an internal UUID); recorded in [`../learnings/actor-token-sub-logical-identity-verification.md`](../learnings/actor-token-sub-logical-identity-verification.md). Needs a live broker.
- **In-cluster enforcement e2e (TODO 11).** Agent gets a credential Secret, authenticates, and a Model-1 grant allows/denies via ext_proc OPA; verified vs demo forged-token behaviour. Needs the broker deployed in KIND; currently exercised via CI e2e.
- **Modes + enablement (P14)** and **strict Gateway decoupling (P15)** carry the source-of-truth/override modes and framework enablement.
