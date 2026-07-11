# P18 — The agent plane on the new topology: PDP, ext_authz, and issuers

**Status**: In progress
**Date**: 2026-07-11
**Realises**: [ADR 0001](../adrs/adr_0001_enforcement-topology-pdp-and-policy-delivery.md) + [ADR 0002](../adrs/adr_0002_agent-identity-issuers-and-aib-boundary.md) (minus DCR, which is P19)
**Branch/PR**: one PR off `main` (post-#260); commit/branch/PR text never references task or phase numbers.

## Design note — how this fits the codebase

- **Enforcement generation** lives in `operator/pkg/security/`: `securitypolicy.go` (jwt_authn + the optional ext_authz seam), `envoyextensionpolicy.go` (ext_proc token-exchange policy — deleted by this phase), `config.go` (the operator-side security config incl. `authorization.provider`/`gatewayExtension`/`extProcUrl` — knobs deleted or re-defaulted), `networkpolicy.go` (kept as-is). Controllers (`agent/mcpserver/modelapi/memorystore_controller.go`) call these constructors per route.
- **Policy compilation** lives in `operator/internal/projection` (grants) + `operator/internal/authz` (rego, JWKS, ConfigMap assembly) driven by `controllers/authz_projection_controller.go` (`PolicyProjector` seam). The actor-only `policy.rego` and `data.kaos.{grants,jwks}` schema are **kept unchanged** this phase; the schema gains only `data.kaos.agents[id].issuer_sub` for the SA identity mapping.
- **AIB adapter** is `operator/internal/authz/adapters/projector_aib.go` (`AIBAdmin`): keeps agent registration + credential mint/rotate/delete; loses service/permission-set projection.
- **Chart** (`operator/chart`): gains `templates/pdp-*.yaml` (OPA Deployment, Service, PDB) behind `security.pdp.enabled`, mounting the projection ConfigMap; `values.yaml` gains `security.pdp` and `security.agentAuth.identity.{provider,...}`, loses `authorization.provider`, `gatewayExtension`, `extProcUrl`.
- **Runtime** (`pydantic-ai-server`): `aib/identity.py` (provider-agnostic token client) gains a file-based provider reading the projected SA token; `aib/instrument.py` propagation is untouched.
- **CLI** (`kaos-cli/kaos_cli/install.py` `_expand_auth_preset`, `system/__init__.py`): presets rewired — `kaos-internal` = SA issuer + PDP, fail-closed, no `agentJwtVerification=skip`; AIB presets select `identity.provider=aib`.
- **Stock OPA image** (`openpolicyagent/opa:latest-envoy`) is the PDP; no KAOS decision-service code exists anywhere.

## TODOs (executed in order; one commit per task; removals strictly before additions)

1. **Remove the ext_proc enforcement path**: delete `envoyextensionpolicy.go` (+ tests) and every call site; delete `extProcUrl` and `gatewayExtension` from operator config, chart values, and the operator ConfigMap template; ext_authz becomes the only enforcement shape (still default-off until task 4). Adjust unit + chart-render tests to the removed state.
2. **Remove AIB-as-enforcement projection**: strip service/permission-set projection from the AIB adapter and projection reconciler (keep registration + credentials); delete the `authorization.provider` knob (the compile pipeline is unconditional when projection is configured); drop broker-authoritative (`external`) data-source mode if present; adjust tests.
3. **Remove enforcement/demo wiring from CLI presets**: drop ext_proc/broker-enforcement flag expansion and `agentJwtVerification=skip` from preset expansion (flag survives only as a hidden advanced option); presets keep installing their IdPs; adjust CLI tests.
4. **Add the PDP to the chart**: OPA (envoy plugin) Deployment (2 replicas) + Service (gRPC 9191) + PDB behind `security.pdp.enabled`, volume-mounting the projection policy ConfigMap; chart-render tests.
5. **Add ext_authz-by-default in the operator**: `SecurityPolicy` ext_authz (gRPC, `failOpen: false`) generated on all internal routes whenever the PDP is enabled, `extAuthzUrl` defaulting to the chart's PDP Service; operator config plumbing for `pdp.enabled`; unit tests for policy generation.
6. **Add the identity issuer abstraction + ServiceAccount issuer (operator/chart)**: `agentAuth.identity.provider: serviceaccount|oidc|aib`; per-agent ServiceAccount + projected token volume (audience `kaos-gateway`) and env pointing at the token path; projection injects the API-server JWKS into `data.kaos.jwks` and emits `data.kaos.agents[id].issuer_sub` mapping; gateway `agent` jwt provider wired per issuer.
7. **Add the file-based token provider in the runtime**: `aib/identity.py` provider that reads (and re-reads on rotation) the projected token file; selected via env; unit tests.
8. **Add the F0 single-issuer mechanism**: one issuer URL value feeds the AIB `publicUrl` and every verifier (gateway provider, JWKS injection); render-time consistency; remove per-surface issuer duplication in CLI/chart.
9. **Rewire CLI presets**: `kaos-internal` = SA issuer + PDP enabled, fail-closed; `aib-only`/`aib-keycloak` = `identity.provider=aib` + same PDP; update preset docs strings and CLI tests.
10. **Validation**: full unit suites (operator, kaos-cli, pais), chart render matrix, KIND e2e with the reworked presets reproducing the phase-1 allow/deny matrix (granted allowed / ungranted denied / no-token denied / PDP-down 403). Never delete an existing KIND cluster.
11. **Docs in lockstep**: rewrite `docs/security/*` to describe only the new topology (PDP, issuers, presets); no references to ext_proc enforcement or the old knobs anywhere in the repo.
12. **REPORT.md** (gitignored, never committed): thorough task-by-task status; contents posted as the PR comment.
