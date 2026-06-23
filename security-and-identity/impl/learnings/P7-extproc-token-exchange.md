# P7 — ext_proc token exchange (learnings)

**Phase**: P7 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Date**: 2026-06-22
**Context**: adding the `ext_proc` token-exchange stage to the gateway pipeline — the operator emits an Envoy Gateway `EnvoyExtensionPolicy` per protected route (gated, default-off) pointing `ext_proc` at AIB's ExtProc service, the broker chart gains an optional ExtProc Deployment, and the CLI provisions and wires the path. Validated live on `kind-kaos-e2e` against Envoy Gateway v1.4.6.

## Key findings

### `ext_proc` is a *different* CRD from `ext_authz` — `EnvoyExtensionPolicy`, not `SecurityPolicy`

Envoy Gateway configures External Processing via `EnvoyExtensionPolicy` (`gateway.envoyproxy.io/v1alpha1`), a sibling CRD to `SecurityPolicy`. They share the `targetRefs` targeting shape (a `HTTPRoute` in group `gateway.networking.k8s.io`) but carry different bodies. Attaching both to the same route layers `ext_authz` (from `SecurityPolicy.spec.extAuth`) and `ext_proc` (from `EnvoyExtensionPolicy.spec.extProc`) in the same pass, after `jwt_authn`. Because they are separate resources with separate reconcilers, token exchange is enabled fully independently of `ext_authz` — hence `ExtProcEnabled()` is independent of `IsOperational()`, and the controllers guard with `IsOperational() || ExtProcEnabled()` while each reconcile self-guards on its own flag.

### Verified `EnvoyExtensionPolicy.spec.extProc` shape (EG v1.4.6)

`kubectl explain envoyextensionpolicy.spec.extProc --recursive` on the live cluster, confirmed by an `Accepted=True` apply:

- `spec.extProc` is an **ordered list**; each entry has `backendRef` (singular) **or** `backendRefs` (list of `{group, kind, name, namespace, port, fallback}`) — we use the list form with `{group:"", kind:Service, name, namespace, port}`.
- `processingMode` carries `request` and/or `response` objects: **presence** of `request` means request headers are sent; the optional `.body` enum (`Streamed`/`Buffered`/`BufferedPartial`/`FullDuplexStreamed`) controls body streaming. The AIB ExtProc only mutates on `RequestHeaders`, so the minimal correct shape is `processingMode: {request: {}}` — header-only, no body.
- The operator-generated policy applied cleanly with `status.ancestors[0].conditions: Accepted/True`.

### The ExtProc service fails closed at startup if it cannot mint its client assertion

The AIB ExtProc performs a `client_credentials` grant against the broker token endpoint **at startup** to obtain the client assertion it later uses for the RFC 8693 exchange. If that grant fails the process exits (fail-closed). Against the stale `aib-dev` broker on the cluster this returned `404 page not found` on `/oauth2/token` — that broker instance predates / does not enable OAuth2-server-mode and has no `extproc-gateway` client. Practical consequences:

- The full delegated-exchange data path requires a broker that (a) runs OAuth2-server-mode and (b) is seeded with the `extproc-gateway` OAuth client, a third-party service, and a delegated grant. The CLI now provisions (a)+(b) under `kaos system install --auth-enabled --token-exchange` via `_build_aib_extproc_args` (chart `extProc.enabled=true`) and `_provision_token_exchange` (admin-API client + dummy service registration).
- A `404` (not `401`) at startup is the tell that the **route** is missing (wrong broker build/config), versus a `401` which would indicate the client exists but credentials are wrong. Useful triage signal.
- Because startup is fail-closed, a misconfigured ExtProc never serves traffic — it crash-loops — rather than silently passing tokens through. Good default, but it means the ExtProc Deployment readiness is a hard dependency for the exchange route.

### Default-off gating keeps internal traffic safe — the headline regression risk is structural, not behavioural

The chief risk was that enabling `ext_proc` would disrupt internal `Agent -> MCPServer/ModelAPI` traffic. The containment is structural: the `EnvoyExtensionPolicy` is only constructed/reconciled when `ExtProcURL` is set, the reconcile is a no-op otherwise, and the existing security-off / ext_authz-only e2e lanes render no `EnvoyExtensionPolicy` at all. Additionally, the ExtProc itself **passes through** any request with no inbound `Authorization` Bearer (it only acts when there is a user subject token to exchange), so even on an attached route the actor-only/autonomous path is untouched.

### Vendored broker chart is the home for the ExtProc component

The broker Helm chart previously deployed only the main broker (enduser `:8000` + admin `:14000`); neither the access-check gRPC service (P2 used a separately-built deployment) nor the ExtProc service had a chart home. P7 adds the ExtProc Deployment+Service to the broker chart, gated by `extProc.enabled` — establishing the pattern (and the eventual home for access-check too). The chart ships a `values.schema.json` with `additionalProperties: false`, so **any** new top-level values block must be added to the schema or `helm lint`/`template` fails with "additional properties 'X' not allowed" — easy to miss.

### CLI default ext_proc URL must match the chart Service name

The plan sketched `aib-extproc.<ns>...` but the chart Service is `<release>-agentic-identity-broker-extproc` (derived from the broker fullname, consistent with `_default_auth_issuer`/`_default_auth_admin_url`). `_default_ext_proc_url` derives from `_auth_broker_fullname(release)` so the operator's `extProcUrl` resolves to the actual rendered Service. Decision recorded here so the deviation from the plan's literal name is intentional and traceable.

### What "triggers" the exchange is transparent subject-token propagation, not agent awareness

A natural objection: the delegated token is needed by the downstream (MCP server / third party), not by the agent, so where is the agent logic that obtains it? There is intentionally none — the agent never fetches or holds the exchanged token. Two distinct tokens ride every protected hop (P6): the **actor token** in `x-agent-authorization` (identifies the agent pod; consumed by `ext_authz`) and the **user subject token** in `Authorization` (identifies the human; consumed by `ext_proc`). The mechanism that makes ext_proc fire is the runtime's propagation middleware in `aib/instrument.py`: `_PropagationMiddleware` captures the inbound `Authorization` bearer into request-local context as `subject_token`, and on every outbound httpx call `_inject_request_headers` re-emits it via `ctx.to_headers()` (alongside the injected `x-agent-authorization` actor token). That outbound request transits the gateway in front of the target MCP/ModelAPI, where `ext_proc` runs the RFC 8693 exchange and **replaces** `Authorization` with the delegated third-party token before it reaches the upstream. So the agent stays unaware by design — it forwards the user's original token, the gateway swaps it, and the MCP server receives an already-exchanged credential. The off-gateway counterpart is `aib/client.py` `exchange_token`/`get_token` (P9), used only when the agent calls a third-party API directly rather than through an ext_proc-protected route.

### The delegated-exchange data path is structurally proven but never executed end-to-end

P7 validated the EnvoyExtensionPolicy **shape** (Envoy Gateway reported `Accepted=True`) and the regression-safety gating, but did **not** run a live `valid user subject -> ext_proc exchange -> upstream sees delegated token` assertion. The cluster's `aib-dev` broker is a stale build returning `404` on `/oauth2/token` (no OAuth2-server-mode, no `extproc-gateway` client), so the actual token swap could not be exercised. The CLI's `kaos system install --auth-enabled --token-exchange` path (`_provision_token_exchange`) was added precisely to seed a broker that can prove this (OAuth2-server-mode + `extproc-gateway` client + a third-party service + a delegated grant), but that live proof remains **outstanding work**: a real end-to-end exchange test against a freshly provisioned `--token-exchange` broker, asserting the upstream observes the exchanged `Authorization` (and that a no-bearer request passes through unchanged). This is the genuine open gap from P7, not the propagation mechanism.

## Carry-forward

- P8 (`spec.security.id` CRD identity override): the resource-naming for the exchange (`resource = {scheme}://{authority}{path}`) must line up with what the broker has services/policies for; CRD-level identity override will influence the actor subject the exchange runs under.
- P6's claim-header spoofing prerequisite: ExtProc consumes the validated `Authorization` **subject token**, not `x-user-claim-*` headers, and the broker re-validates `subject_token` during the exchange — so the forged-claim-header risk does not reach the exchange. If a future change has ExtProc read claim headers, the ingress strip from the P6 learnings becomes mandatory.
- **Open follow-up — live end-to-end exchange test**: stand up a `--token-exchange`-provisioned broker (OAuth2-server-mode + `extproc-gateway` client + registered third-party service + delegated grant) on KIND and assert the full data path: a request carrying a valid user subject token has its `Authorization` replaced by the exchanged delegated token at the MCP/ModelAPI upstream, while a no-bearer request passes through unchanged. P7 proved only the policy shape; this proves the swap. Suggested home: the enforcement/hardening phase e2e suite.
