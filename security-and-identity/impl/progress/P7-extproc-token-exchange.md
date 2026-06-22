# P7 — ext_proc token exchange (progress)

**Phase**: P7 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P7-extproc-token-exchange.md`](../../plan/P7-extproc-token-exchange.md)
**Status**: Complete — the operator now emits an Envoy Gateway `EnvoyExtensionPolicy` per protected route (gated, default-off) that points the gateway `ext_proc` stage at AIB's ExtProc token-exchange service, the broker chart gained an optional ExtProc Deployment+Service, and the CLI provisions and wires the whole token-exchange path. The generated `EnvoyExtensionPolicy` shape was confirmed `Accepted=True` live on Envoy Gateway v1.4.6.
**Date**: 2026-06-22
**PR**: stacked onto `feat/gateway-user-authentication` (the P6 branch)

## Outcome

Before P7 the gateway pipeline was `jwt_authn (P6) -> ext_authz (P2) -> upstream`: it authenticated the agent actor and the user subject and authorized the actor->resource edge, but could not turn a verified user subject token into a delegated third-party access token for a protected downstream call. P7 adds the **`ext_proc` token-exchange** stage, completing `jwt_authn -> ext_authz -> ext_proc -> upstream`. When token exchange is enabled, the operator generates a separate `EnvoyExtensionPolicy` (a *different* CRD from `SecurityPolicy`, both `gateway.envoyproxy.io/v1alpha1`) that runs the AIB ExtProc service after `ext_authz` in the same pass; ExtProc performs an RFC 8693 token exchange against the broker token endpoint and replaces the upstream `Authorization` header with the exchanged token. The whole path is opt-in and independent of `ext_authz`: with no `extProcUrl` configured no `EnvoyExtensionPolicy` is rendered and existing installs are unchanged.

## Deliverables

| Area | Deliverable |
|---|---|
| Operator config | `pkg/security/config.go` — `ExtProcURL` field + `SECURITY_AGENT_AUTH_EXT_PROC_URL` env, read in `GetConfig()`; `ExtProcEnabled()` (true when `ExtProcURL` set, independent of `IsOperational()`); `ExtProcBackendRef()` reusing a shared `parseServiceHostPort` helper factored out of `ExtAuthzBackendRef`. |
| EnvoyExtensionPolicy | `pkg/security/envoyextensionpolicy.go` — `EnvoyExtensionPolicyGVK`, `constructEnvoyExtensionPolicy` (unstructured; `spec.targetRefs` → HTTPRoute, `spec.extProc[].backendRefs` from `ExtProcBackendRef()`, `processingMode.request{}` header-only), `ReconcileEnvoyExtensionPolicy` (create-or-update + owner ref; no-op unless `ExtProcEnabled()`). Mirrors `securitypolicy.go`. |
| Controllers + RBAC | All three controllers (`agent`/`mcpserver`/`modelapi`) broadened their guard to `IsOperational() \|\| ExtProcEnabled()`, share a single `policyParams`, and call both `ReconcileSecurityPolicy` and `ReconcileEnvoyExtensionPolicy` (each self-guarded). `envoyextensionpolicies` RBAC added via a kubebuilder marker in `main.go`, regenerating `config/rbac/role.yaml` and mirrored into `chart/templates/kaos-operator-rbac.yaml`. |
| Operator chart | `chart/values.yaml` `security.agentAuth.extProcUrl` (empty default); `templates/operator-configmap.yaml` renders `SECURITY_AGENT_AUTH_EXT_PROC_URL` only-when-set, mirroring `extAuthzUrl`. |
| AIB broker chart | `charts/agentic-identity-broker/templates/extproc.yaml` — optional ExtProc Deployment+Service (`aib-extproc`, gRPC `:50051`, `Dockerfile.extproc` image) gated by `extProc.enabled` (default false), configured via `EXTPROC_*` env from new `extProc.*` values; token endpoint/issuer default to the in-cluster broker enduser service. `values.schema.json` extended so the block passes chart validation. (committed on the AIB deployability-foundation branch.) |
| CLI | `kaos_cli/install.py` — `AUTH_EXT_PROC_PORT=50051`, `_default_ext_proc_url`, `_build_aib_extproc_args` (enables the chart ExtProc component), `_provision_token_exchange` (best-effort admin-API registration of the ExtProc OAuth client + dummy third-party service), `_build_auth_operator_args` extended with `ext_proc_url`. New flags `--token-exchange/--no-token-exchange` (default on under `--auth-enabled`) and `--ext-proc-url`. |

## Validation

- **Operator unit + integration tests**: `go test ./pkg/security/... ./controllers/...` green — `ExtProcEnabled()`/`ExtProcBackendRef()` parsing across `name:port`/`name.ns:port`/`name.ns.svc.cluster.local:port` + error cases, `EnvoyExtensionPolicy` targetRefs + backendRef shape, and the construct/reconcile no-op when disabled. `gofmt`/`go vet` clean; `make manifests generate` shows only the new `envoyextensionpolicies` RBAC rule, no other drift.
- **Operator chart**: `helm template` renders `SECURITY_AGENT_AUTH_EXT_PROC_URL` when set and nothing when absent; `helm lint` clean.
- **AIB broker chart**: `helm template --set extProc.enabled=true` renders the ExtProc Deployment+Service with the `EXTPROC_*` env, `:50051` port, and `appProtocol: grpc`; the default render emits no ExtProc objects; `helm lint` clean.
- **CLI**: 83 tests green incl. new `_default_ext_proc_url`, `_build_aib_extproc_args`, and `_build_auth_operator_args` extProcUrl on/off assertions.
- **Live on KIND (`kind-kaos-e2e`, Envoy Gateway v1.4.6)**: applied the operator-shaped `EnvoyExtensionPolicy` (echo backend + HTTPRoute + ext_proc attachment) — Envoy Gateway reported `Accepted=True` ("Policy has been accepted"), confirming the exact `spec.extProc[].backendRefs` + `processingMode.request{}` shape against the live CRD.

## Notes

- The full delegated-exchange **data path** (valid user subject -> replaced upstream `Authorization` with the exchanged token; no-bearer -> pass-through; consent -> `error_uri` JSON-RPC `-32042`) is **local-KIND only** while the broker/ExtProc images are unpublished, and additionally requires a broker running OAuth2-server-mode seeded with the `extproc-gateway` client + a third-party service + a delegated grant. The stale `aib-dev` broker on the cluster returns `404` on `/oauth2/token`, so the complete proof belongs to the `kaos system install --auth-enabled --token-exchange` path (which the CLI now provisions) and is documented in REPORT.md. The operator-generated policy shape itself is validated independently (EG-accepted).
- The headline regression risk — internal `Agent -> MCPServer/ModelAPI` traffic must be unaffected when `extProcUrl` is set — is structurally contained: the `EnvoyExtensionPolicy` only renders when `extProcUrl` is configured, the reconcile is a no-op otherwise, and the existing security-off / ext_authz-only e2e suites stay green.
- Out of scope (later phases): `spec.security.id` CRD identity override (P8); refresh-ahead/reactive actor-token lifecycle in the SDK (P9); per-tool/argument body-level authorization; injecting `x-principal`/`x-actor` context headers via ExtProc; publishing and upstreaming the broker/ExtProc images.
