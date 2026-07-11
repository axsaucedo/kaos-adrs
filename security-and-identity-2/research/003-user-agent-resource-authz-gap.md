# Research 003 — The USER + Agent + Resource authorization gap

**Date**: 2026-07-11
**Sources**: [model-parity learnings](../../security-and-identity/impl/learnings/opa-extproc-authz-model-parity-and-oauth-path.md), the published policy data contract in KAOS PR `axsaucedo/kaos#267` (`docs/security/authorization.md`, `operator/internal/authz/data-schema.md`), AIB code inspection (fork access-check + upstream `#222`).

This document pins down the flaw the project owner identified: **nothing in the implemented stack authorizes the full (user, agent, resource) triple.** Everything shipped keys on the actor alone. The design phase must decide how the user dimension enters the decision — this is a data-model and policy-input question, not a new enforcement mechanism.

## What is implemented today: actor-only

- **The published contract is two-dimensional.** `data.kaos.grants` maps `kaos://agent/<ns>/<name>` → array of resource ids. There is no key, claim, or field for the subject (user) anywhere in the schema.
- **The static rego matches the contract.** The decision is `resource_id in data.kaos.grants[actor_id]`; the subject bearer token, when present, is never consulted for the allow/deny outcome (it is only what triggers evaluation at all — see G1 below).
- **The projector cannot produce user facts.** `AuthzProjectionReconciler` derives grants from `Agent`/`MCPServer`/`ModelAPI` CRDs (`mcpServers`, `agentNetwork.access`, model references). No KAOS CRD carries user identity, so automated mode structurally cannot emit a user dimension — a user-aware model needs a new fact source, not just new rego.

Consequence: today, if user Alice may use agent `researcher` but user Bob may not, KAOS cannot express it. Any user whose token passes gateway `jwt_authn` gets identical authorization outcomes for a given agent.

## The mechanism already carries the missing facts

The phase-1 parity analysis established that both authorization models assemble the same four fact sources into one OPA input: (1) the subject token claims, (2) the actor token claims, (3) the request attributes (target resource, path, method), (4) the policy data document. The subject token — with the user's `sub`, `preferred_username`, `realm_access.roles`, `groups` from Keycloak — **is already parsed and present in the input document today; the rego simply ignores it.**

So the gap is confined to two artifacts:

- the **data shape** (`data.kaos.grants` needs a user dimension or a parallel `data.kaos.user_grants` / role-mapping document), and
- the **rego** (a conjunctive rule: subject-condition AND actor→resource grant).

The enforcement mechanism, the header plumbing (`Authorization`, `x-agent-authorization`, `x-kaos-target-resource`), and the ConfigMap delivery all carry over unchanged.

## G1 makes the user dimension partly fictional under the current topology

Under the current ext_proc wiring, evaluation only triggers when a subject bearer is present (no-bearer requests pass through — the G1 gap). Two corollaries for the new design:

- A user-aware policy is only as strong as the guarantee that requests *with* a user context actually present it — today an agent can strip the user token and skip evaluation entirely.
- Autonomous (no-user) traffic needs an explicit policy stance: "no subject" must become a first-class input value the rego reasons about (allow per agent-grants only, or deny, per deployment posture) rather than a bypass. This requires an enforcement point that runs unconditionally — a topology property, decided in the topology ADR, that the current AIB ext_proc cannot provide (research/001).

## Prior art for the (user, agent, resource) triple

- **AIB's fork-only access-check service** is the only component in the whole stack that already models the triple: its decision core walks PermissionSets for agent→service (platform grant) and then, when the subject principal differs from the agent, requires an active `UserGrant` for the (principal, agent) pair — with distinct deny reasons `platform_grant_missing` vs `user_grant_required`, and per-grant service subsets plus expiry (`GrantedPermissionSetEntry.IncludedServiceIDs`, `ValidUntil`). The fork is not a viable dependency (research/001), but the shape — *platform grant on the actor AND user grant on the (user, agent) pair, each independently deniable* — is directly reusable as the KAOS data model.
- **AIB `#222`'s rego input** likewise exposes subject and actor claims side by side; its example policies just don't correlate them.
- **Keycloak** natively expresses user→agent authorization as claims: realm/client roles, groups, or audience per agent client. A "user may use agent X" fact can arrive **inside the subject token** (role `agent:researcher`, group `/agents/researcher`) instead of inside projected policy data — no new CRD or admin API needed, at the cost of coupling grant administration to the IdP.

## Candidate sources for the user dimension (for the ADR to weigh)

1. **Keycloak claims** — user→agent facts as roles/groups in the subject token; rego checks token claims against the requested agent. Admin surface is Keycloak; zero KAOS storage.
2. **KAOS-owned grant data** — a user dimension in the projected data document (e.g. `data.kaos.user_grants: {"<user-sub-or-role>": ["kaos://agent/ns/name", ...]}`), authored via the existing manual/operator-rego modes or a future CRD. Admin surface is KAOS; keeps the IdP generic.
3. **AIB UserGrant-shaped data** — adopt the access-check *model* (platform grant + user grant, expiry, service subsets) as the schema for option 2's data document, whether the facts come from Keycloak, CRDs, or a future broker sync.

These are not mutually exclusive — 3 is a schema choice that 1 and 2 can both populate. The real decisions are: where the user facts live, who administers them, and what the rego's conjunction looks like — which belong to the authorization-model ADR.
