# Manual end-to-end validation plan — phase 2 (on-the-wire, bypass-proof)

**Status**: Proposed
**Date**: 2026-07-12
**Purpose**: prove, with real HTTP requests and real tokens on a NetworkPolicy-enforcing cluster, that the shipped authorization (P18 PDP + P19 user/agent/resource model) actually accepts and rejects the right traffic **and cannot be worked around** — mirroring the phase-1 `manual-e2e-*` and `aib-ext-proc-limitations` learnings that surfaced the ext_proc gap. Not "CRDs exist" — actual allow/deny status codes, plus adversarial attempts to bypass the gateway.

## Why a new cluster (Calico, not kindnet)

The existing `kaos-e2e` cluster uses **kindnet**, which does **not enforce NetworkPolicy** (phase-1 learnings deferred bypass-prevention as "Calico-gated"). To prove the core "you cannot work around the gateway" claim — that a workload cannot reach a protected resource directly on its ClusterIP, skipping the PDP — the cluster's CNI must actually enforce NetworkPolicy. So this plan stands up a **separate KIND cluster with Calico** (`disableDefaultCNI: true` + Calico install) and **never touches `kaos-e2e`**. The Calico cluster, with the walkthrough deployed, is left running for the user to drive.

## Postures under test

1. **`kaos-internal`** — SA agent identity, no external IdP (agent plane) + `gateway-strict`.
2. **Keycloak user plane** — user identity via Keycloak (`aib-keycloak` or the keycloak-backed path) + `gateway-strict`.
3. **`oidc-keycloak`** — DCR agent identity (the path the P19 review found broken and fixed; must prove end to end).
4. **AIB** — best effort; document gaps honestly (task-10 already saw the upstream ext_proc pod crash-looping).

## Flows to validate — each is a real request with an expected status, captured as evidence

### A. Agent plane (`kaos-internal`)
- autonomous agent → **granted** MCP/ModelAPI/memory = **200**
- → **ungranted** resource = **403**
- valid actor token, **no subject** = **403** (the P19 semantic shift — actor-only no longer suffices)
- **no token** at all = 401/403
- **PDP scaled to 0** = 403 (fail-closed), then recovery = 200
- **forged / wrong-audience / wrong-alg** actor token = 403
- **spoofed `x-kaos-target-resource`** (claim granted A while hitting B's path) = **403** (header-spoof fix proven on the wire)

### B. User plane (Keycloak)
- user in group `researchers` + matching `AccessGrant` → agent at **entry** = **200**
- user **without** a matching grant = **403**
- user token with **wrong audience** = 403
- `AccessGrant` shows `Enforced=False/NoUserIdentityProvider` without userAuth, **flips to `Enforced=True`** once Keycloak user plane is enabled
- propagated user subject verified on an **internal** hop (agent→resource carrying the user token)

### C. `oidc-keycloak` (DCR agent, the fixed path)
- an OIDC agent obtains a token via `client_credentials` against **Keycloak's** token endpoint and makes an **authorized** call = **200**
- its token resolves to the logical grant id via the `azp` mapping (prove the fix, not just registration)

### D. Bypass prevention — THE "can't work around it" proof (Calico + `gateway-strict`)
- a workload calling a protected resource **directly on its ClusterIP** (skipping the gateway) is **BLOCKED** by NetworkPolicy (connection refused/timeout) — **not** a 200
- direct pod→pod and pod→PDP traffic blocked
- confirm the **only** viable application path is through the gateway, where ext_authz runs — so the PDP cannot be skipped
- attempt to reach a resource with a valid actor token but **off the gateway path** = fails at the network layer, before any policy

### E. AIB path (best effort)
- `aib`/`aib-keycloak` agent identity + Keycloak user; validate what works, **document gaps** (extproc crash-loop, audience requirements) in the learnings — a finding is a deliverable, not a failure to hide.

## Deliverables

1. **A running Calico KIND cluster** with the walkthrough workloads (agents, MCP/ModelAPI, Keycloak, AccessGrants) deployed, that the user can drive by hand. `kaos-e2e` left untouched.
2. **Walkthrough doc(s)** in `docs/security/` — copy-paste reproducible: the exact `kaos system install` command, resource manifests, token-minting commands, and `curl` calls with **expected status codes** per posture (agent plane, user plane, oidc, bypass). Either extend the plane-based walkthroughs with a "run it yourself / expected allow-deny" section or add a dedicated `walkthrough-validation.md`.
3. **Learnings doc** in `kaos-ai-docs/security-and-identity-2/impl/learnings/manual-e2e-phase2-validation.md` — what was validated live (with captured status codes as evidence), what remains deferred, and any gaps found, in the honest `aib-ext-proc-limitations` style (a "does not work / here's why" section if we hit one).
4. **Evidence artifacts** under `./tmp` (curl outputs, the allow/deny status matrix as JSON).

## Execution (Codex, high effort, detached, iterative)

- **Step 1** — create the Calico KIND cluster (new name, e.g. `kaos-manual-e2e`; `disableDefaultCNI: true` + Calico). NEVER delete or modify `kaos-e2e`.
- **Step 2** — install `kaos-internal` + `gateway-strict`; deploy walkthrough workloads; run flows **A** and **D**; capture evidence.
- **Step 3** — enable the Keycloak user plane; run flows **B** and **C**; capture.
- **Step 4** — AIB best effort (**E**); document gaps.
- **Step 5** — write the learnings doc + the walkthrough; verify the walkthrough is copy-paste reproducible end to end on the running cluster; leave the cluster healthy and running.

Codex hard rules: never touch `kaos-e2e`; the Calico cluster is separate and disposable-by-the-user; all evidence under `./tmp`; **document gaps honestly** — if a flow does not behave as designed, that is the single most valuable output (this is how the ext_proc limitation was found). Fixes to product code discovered during validation are allowed and committed separately, but the primary deliverable is the validated walkthrough + learnings.

## Scope decisions (confirmed)

- **Cluster**: **tear down the old `kaos-e2e` cluster** and stand up a fresh KIND cluster with **Calico** (`disableDefaultCNI: true` + Calico) so NetworkPolicy is enforced and flow D is provable. The prior "never delete `kaos-e2e`" rule is explicitly lifted for this pass. Leave the new Calico cluster running with the walkthrough deployed.
- **AIB depth**: **best-effort with honest gap documentation** — attempt the `aib-keycloak` posture, validate what works, record gaps in the learnings; do not block on AIB being healthy.
