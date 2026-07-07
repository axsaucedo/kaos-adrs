# ADR 0001 — Enforcement topology and policy engine

- **Status.** Proposed
- **Date.** 2026-07-07
- **Component.** 1 of 4 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [research/005](../research/005-identity-architecture-and-mcp-gateway.md), [research/006](../research/006-crd-sync-identity-gateway-sidecar-and-autonomous.md), [target-picture/007](../target-picture/007-decision-identity-model-and-source-of-truth.md), [model-parity learnings](../impl/learnings/opa-extproc-authz-model-parity-and-oauth-path.md)
- **Resolved by.** [ADR 0003](./adr_0003_authorization-models-and-policy-data.md) (what the engine reads), [ADR 0004](./adr_0004_component-architecture-and-projection.md) (how data reaches the engine)

## Context

KAOS routes all agent and MCP traffic through an Envoy Gateway (Gateway API). Identity and authorization are enforced at that gateway rather than in the agent runtime, which is not a trust boundary. The earlier design placed a standalone AIB **ext_authz access-check service** (AIB PR #398) behind a gateway `SecurityPolicy`, alongside a separate ext_proc filter for token-exchange. AIB `main` (feature #222) has since embedded **OPA directly inside the ext_proc token-exchange filter**, so a single gateway hook performs both RFC 8693 token-exchange and the authorization decision. PR #398 (standalone decision service) and PR #399 (Python SDK) are abandoned; the KAOS build target is AIB `main` (including #222) plus PR #397 (deployability: public images, Helm chart, KIND target, optional ext_proc deployment).

This ADR settles where the authorization decision is made and by what engine. It does not decide what facts the policy evaluates ([ADR 0003](./adr_0003_authorization-models-and-policy-data.md)) or how KAOS delivers them ([ADR 0004](./adr_0004_component-architecture-and-projection.md)).

## Decision

### Single enforcement point: OPA embedded in AIB ext_proc

Authorization is enforced by **OPA embedded in the AIB ext_proc filter (#222)**, invoked on the gateway request path via the ext_proc `EnvoyExtensionPolicy` that KAOS already renders. This is the single decision point for **both** authorization models in [ADR 0003](./adr_0003_authorization-models-and-policy-data.md); the models differ only in the data OPA reads, not in the engine or the hook. The ext_proc filter runs the token-exchange and the OPA evaluation together, so there is no second network hop to a separate decision service.

OPA sees **four fact sources simultaneously** in one input: the subject identity decoded from the `authorization` header, the actor identity decoded from the `x-agent-authorization` header, KAOS-owned `data.kaos.grants` (Model 1 data), and broker `context.granted_permission_sets` from token-exchange (Model 2 data). The ext_proc input builder passes all HTTP headers through verbatim. A single rego policy therefore has everything needed to decide subject-plus-actor-plus-resource access under either model.

### ext_authz retained as an optional, default-off generic seam

The operator's ext_authz `SecurityPolicy` generation is **generalised, not deleted**. It no longer assumes the AIB #398 decision service; it becomes an optional, default-off seam pointing at a configurable ext_authz backend. Its purpose is a **KAOS-run OPA for AIB-less or standalone enforcement** — the path that lets coarse authorization work without deploying AIB (paired with the AIB-less identity issuer in [followups](../plan/followups.md)). Default enforcement is the AIB ext_proc OPA above; the ext_authz seam stays cheap to enable but off by default. Removing the #398 dependency therefore means dropping the *assumption* that ext_authz targets AIB, not removing the capability.

### Coarse granularity

Enforcement is **coarse**: subject × actor × resource (agent, MCP server, model API), not MCP tool-level or method-level. The ext_proc input does expose MCP call metadata (`input.type = mcp_tool_call`), but tool-level policy is out of scope for this version.

### Reload posture: static rego, data hot-reload deferred

OPA in #222 has two mutually exclusive load modes: `policy.path` compiles once and is **static** (a data change requires an ext_proc restart), while `policy.config_file` runs the OPA SDK bundle mode with background-poll **hot-reload**. KAOS ships a **static generic rego** and, for Model 1, starts with `policy.path` (restart-on-data-change), which is the simplest correct posture. ConfigMap-as-local-bundle hot-reload is a later enhancement requiring a spike; the rego stays static in either case and only the data is regenerated. See [ADR 0004](./adr_0004_component-architecture-and-projection.md) for the delivery mechanics.

### G1 autonomous gap: enforcement requires a subject bearer

A hard constraint of #222: OPA only runs when a **subject bearer** (an `Authorization` header) is present; with no bearer the ext_proc filter passes through **without** invoking OPA. User-present flows ("user A via agent B") therefore always enforce, but a purely autonomous agent action with no user token bypasses OPA. This version treats autonomous-mode enforcement as **unsupported** (deferred). Closing it needs either an AIB change or treating the actor token as the bearer in autonomous flows; it is recorded but not built here.

## Consequences

Positive: one engine, one gateway hook, and one policy surface serve both authorization models, eliminating the separate decision-service hop and its deployment; the four-fact-source input gives full model parity by construction; keeping ext_authz as a generic seam preserves an AIB-less enforcement path without coupling the default to it. Negative: enforcement is bound to AIB ext_proc being deployed for the default path, and the static `policy.path` posture means Model-1 data changes restart the ext_proc pod until bundle hot-reload lands; autonomous-mode actions are unprotected in this version. Follow-on: [ADR 0003](./adr_0003_authorization-models-and-policy-data.md) fixes the fact schema and populator modes; [ADR 0004](./adr_0004_component-architecture-and-projection.md) fixes data delivery and the bundle-hot-reload spike.

## Alternatives considered

Keep the standalone AIB ext_authz decision service (#398) — rejected: #222 folds OPA into ext_proc, so a second hook and deployment is redundant. Fully delete ext_authz generation — rejected: it is the cheapest seam for a KAOS-run OPA in AIB-less setups, which is a wanted capability. Bundle-server hot-reload from day one — deferred: adds a deployment; static `policy.path` is correct and simplest to start. MCP tool-level granularity — out of scope: coarse subject/actor/resource is sufficient for this version.
