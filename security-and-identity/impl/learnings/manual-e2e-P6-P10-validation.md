# Manual end-to-end validation (P6-P10 authz baseline + P4 enforcement)

This is the brief, glaring-bug-focused manual end-to-end pass requested between P10 and P11. Its purpose was to stand up a real-mostly in-cluster deployment (real operator, agent, gateway, broker; mockable third-party) and validate that the security/identity work actually enforces something on the real, P4-routed data path — not just on synthetic requests aimed at the gateway URL. The headline outcome is that the P4 enforcement guarantee is genuinely validated end-to-end, and two real integration bugs were found.

## Environment

A dedicated Calico KIND cluster (`kaos-sec-e2e`) was used because the default kindnet CNI does not enforce `NetworkPolicy`; Calico does. Cluster config: `disableDefaultCNI: true`, pod subnet `192.168.0.0/16`, Calico v3.27.3. KAOS was installed from the P4 branch operator image with auth wiring plus NetworkPolicy and gateway routing enabled (`--auth-enabled --no-user-auth --no-token-exchange --network-policy --gateway-routing`), without the full broker/Keycloak stack for the core enforcement checks. A real Agent + MCPServer (python-string echo) + Proxy ModelAPI were deployed into namespace `e2e-sec`. The gateway received a MetalLB address (`172.18.0.200`).

## What was validated (genuine end-to-end)

The reason P4 was resequenced before this e2e is that KAOS injects direct `svc.cluster.local` URLs for MCP/ModelAPI/peer endpoints, so without NetworkPolicy + gateway routing the internal agent->MCP/ModelAPI traffic bypasses the Envoy Gateway entirely and gateway authz is never exercised on the real path. This pass confirms the resequencing was correct and that the mechanism works:

- All three per-workload NetworkPolicies were generated (agent, mcp, modelapi), ingress-only, allowing traffic only from the gateway and operator namespaces.
- Agent environment was gateway-routed: `MCP_SERVER_e2e-echo-mcp_URL` and `MODEL_API_URL` pointed at `http://172.18.0.200/e2e-sec/...` rather than the direct cluster-local service URLs.
- TEST A (direct ClusterIP from a scratch pod in the `default` namespace): connection BLOCKED (curl timeout) — Calico enforces the NetworkPolicy, so the gateway bypass is closed.
- TEST B (same request via the gateway path): connection ALLOWED but returned HTTP 401 with `www-authenticate: Bearer realm=...` — the gateway's JWT SecurityPolicy fail-closes unauthenticated traffic.

Together these prove the complete thesis: the direct bypass is blocked, internal traffic is rerouted through the gateway, and the gateway enforces authz on that real path. Before P4 this end-to-end path did not exist.

## Bug found and fixed: missing Gateway RBAC

The agent stayed `Waiting: ModelAPI is not ready` even though the ModelAPI reported `ready: true`. Operator logs showed `gateways.gateway.networking.k8s.io is forbidden: ... cannot list resource "gateways"`. The gateway-routing code reads the Gateway status address, which makes controller-runtime establish a get/list/watch informer on `gateways`; P4 had only added `httproutes` RBAC. The failed watch wedged reconciliation, and routing would otherwise have silently fallen back to direct URLs (defeating the whole point of routing). Fixed by adding a `gateways` get/list/watch RBAC marker to the operator, regenerating `role.yaml`, and mirroring the rule into the chart RBAC template. After the fix the watch errors cleared and the agent reached `Ready`. This is exactly the class of bug the manual e2e was meant to surface — it is invisible to unit tests because they do not exercise the live informer/RBAC interaction.

## Finding: dev-preset broker omits the access-check ext_authz service

For the positive (valid-token -> 200) path the broker was installed from its chart dev preset (in-memory storage, local OAuth2, `X-Remote-User` preauth — zero external dependencies). The broker came up healthy and serves its JWKS at `/oauth2/jwks.json`, which is exactly the URI the operator wires into the gateway SecurityPolicy `jwt.remoteJWKS`, so the JWT validation chain is correctly wired end-to-end.

However, the generated SecurityPolicy also wires an `extAuth.grpc` backend to `aib-access-check-grpc` (the access-check ext_authz service), and the dev preset does not deploy that service. The SecurityPolicy therefore reports `Accepted=Invalid` with `ExtAuth: service aib-system/aib-access-check-grpc not found`. Importantly, Envoy Gateway still fail-closes the JWT portion in this state (unauthenticated requests get 401), so enforcement is not silently dropped. But because the extAuth backend is absent, even a valid broker-issued token cannot reach a 200 — it would fail-closed at the missing extAuth backend. So the positive 200 path is not reachable from the brief dev bring-up alone; it requires the access-check component plus a granted authorization edge and a properly minted actor token (the integration of the P2/P11 access-check and the P3/P5/P9/P10 credential-provisioning chain).

This is a genuine integration gap worth tracking: a KAOS `--auth-enabled` install that wires ext_authz to `aib-access-check-grpc` against a dev-preset broker produces an `Accepted=Invalid` SecurityPolicy. Either the AIB dev chart should also deploy the access-check service, or the KAOS install should not wire ext_authz when the target broker does not provide it (e.g. gate ext_authz wiring on access-check availability, or surface a clearer status). Tracked as a follow-up for P11/P12.

## Scope boundary (deliberate, per the brief)

The request was explicitly a brief pass to catch glaring bugs, not an exhaustive positive-path matrix. The deny path, the gateway-routing repoint, and the JWT enforcement layer were validated genuinely end-to-end on the real P4-routed path, and the JWKS wiring to the live broker was confirmed. The full positive-decision matrix (Keycloak user-JWT for P6, ext_proc delegated token swap for P7, identity-override-driven actor token + SDK mint/refresh/401-retry for P8/P9, and watch/leader/rotation/write-back for P10) each require the heavier multi-component stack (access-check service + sync-provisioned agent credentials + Keycloak + ext_proc) and were validated component-wise within their own phases. They are recommended as a dedicated full-stack e2e follow-up once the access-check service is part of a reproducible dev bring-up. The enforcement baseline established here is the known-good state that P4 (Calico + TLS) must not regress.

## Recommended automated follow-ups

- An operator e2e assertion (CI-runnable on kindnet, since generation does not need enforcement) that `--network-policy --gateway-routing` causes the operator to (a) generate the three NetworkPolicy objects and (b) inject gateway-routed MCP/ModelAPI URLs into the agent. Enforcement itself cannot be asserted in the kindnet CI and is documented as a Calico-only manual check.
- Add the `gateways` RBAC rule to any RBAC regression check so the informer/watch dependency is not dropped again.
- Track the dev-preset access-check omission so a future reproducible full-stack e2e can assert the positive 200 path.
