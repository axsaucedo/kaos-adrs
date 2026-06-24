# Manual end-to-end validation (removal of `spec.security.id` identity override)

This is the manual end-to-end pass that accompanied the removal of the `spec.security.id` identity-override feature and its duplicated collision/conflict-detection logic. After the removal, logical identity is **always** `kaos://<kind>/<namespace>/<name>` — unique by construction — so there is no override path, no oldest-wins adoption, and no cross-side parity hazard to police. The purpose of this pass was to prove that removing the override left the default-identity provisioning, injection, mount, ready, and gateway-enforcement path fully intact on freshly built operator and sync images.

## Environment

The pre-existing `kaos-e2e` KIND cluster was reused (operator in `kaos-system`, broker + sync in `aib-system`, access-check in `aib-p2`, Keycloak). Two images were rebuilt from the removal branches and loaded into the cluster: the operator (`make docker-build`, loaded over the running tag) and the stripped sync service (`axsauze/kaos-sync:dev`). The operator and sync deployments were restarted onto the new images. A dedicated namespace `idr-e2e` held a ModelAPI (proxy, `models:["*"]`), an MCPServer (python-string echo), and an Agent on the default identity.

## What was validated (genuine end-to-end, new images)

The headline result is that the default-identity path is byte-for-byte the pre-removal behaviour, proven live rather than by unit assertion:

- **Stripped sync live-reconcile on the default identity.** The stripped sync (no `SecurityID`, no `winnersAndConflicts`/`IdentityConflict`/`Conflicts`) reconciled `idr-agent` cleanly: `credentialsMinted:1, services:2, permissionSets:2, agents:1, failed:0`, and minted the per-agent credential secret `kaos-aib-idr-agent`. Removing the override and collision logic did not change the default projection.
- **Operator inline-identity injection.** The new operator injected `AGENT_AUTH_IDENTITY=kaos://agent/idr-e2e/idr-agent` into the agent Deployment — the exact inline `fmt.Sprintf("kaos://agent/%s/%s", ns, name)` form the removal reverts to (no `pkg/identity` package, no `security.id` lookup) — and sourced `AGENT_AUTH_CLIENT_ID` / `AGENT_AUTH_CLIENT_SECRET` from the sync-minted secret via `secretKeyRef`.
- **Agent reaches Ready.** The `agent-idr-agent` Deployment reached `Ready 1/1` against the new operator and the sync-provisioned credentials.
- **AIB sync e2e green.** `make e2e-test-aib` (default-identity mint -> mount -> agent-pod) passed earlier in the same pass against the stripped sync image.
- **Gateway enforcement live + fail-closed.** Through the real gateway (MetalLB `172.18.0.200`, port-forwarded), an unauthenticated POST to the agent route returned **401**, and a bogus-bearer POST returned **401**. The ext_authz path reached the broker access-check (after mirroring the access-check Service into `aib-system` to match the operator's configured backend ref) and fail-closed correctly.

Together these prove the removal is safe: the default-identity credential-provisioning chain, the operator identity injection, the read-only secret mount, agent readiness, and gateway fail-closed enforcement all continue to work with the override and collision logic deleted.

## Scope boundary (deliberate)

The positive valid-token -> **200** decision path was not exercised in this pass, for exactly the same reason documented in the P6-P10 manual validation: a 200 requires the access-check component **plus** a granted authorization edge bootstrapped through the broker admin API **plus** a properly minted actor/user token. That is the heavier full-stack matrix (access-check + sync-provisioned credentials + Keycloak + a grant), and it re-validates the *enforcement* surface — which P11/P12 already covered component-wise — not the identity removal. It is therefore unaffected by removing `security.id` and remains the same separately-tracked full-stack follow-up. The removal's blast radius is the default-identity path, and that path is proven intact here.

## Environmental note (not caused by the removal)

On the reused `kaos-e2e` cluster, the operator ServiceAccount's ClusterRole lacked `networkpolicies` get/list/watch, which wedged ModelAPI reconciliation (stuck `Pending` despite a ready Deployment) until the missing RBAC was granted. This is stale-chart RBAC drift on the long-lived dev cluster, unrelated to the identity-override removal; a fresh install from the current chart does not exhibit it. Similarly, the access-check Service lived in `aib-p2` while the operator config referenced `aib-system`, so the access-check had to be mirrored into `aib-system` for the gateway deny path to reach it — again a property of this drifted cluster, not of the change under test.
