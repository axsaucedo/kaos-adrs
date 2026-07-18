# Memory v2: compound attribution, per-session tiers, read-scope policy, and OIDC per-user

Learnings from the memory scoping redesign delivered across the stack PRs #280 (compound attribution + per-session windows), #282 (read-scope policy + level tool), #286 (OIDC per-user), plus the auth-gateway guard (#285). Grounded in a Mem0 spike, a live cluster validation (17/17 cases on a reused auth cluster), and several bug-fix regressions — including one caught only at merge time by the committed example E2E. The stack merged to `main` on 2026-07-18 (merge commits `8d6191d2`, `f1d05d90`, `82fcfa5e`).

## What changed and why

The pre-v2 model had three defects, all surfaced while writing the memory blog post:
- **Attribution loss**: long-term writes carried exactly one owner key, so "forget user X" could not reach the user's contributions in shared partitions, and user/fleet reads could not aggregate across agents.
- **Window drift**: short-term window and medium-term summary were keyed by the scope owner, so concurrent sessions in a shared scope interleaved one verbatim window — contradicting the recorded architecture (conversational tiers are session-scoped).
- **Rigid read policy**: an agent read exactly one scope; no baseline-recall of fleet knowledge, no model-driven level selection.

## Mem0 spike findings (pinned `mem0ai==2.0.10`)

Validated before committing the write contract:
- **Compound writes are free**: `add()` with `user_id + agent_id` costs the same as a single-id write — one extraction LLM call, one record, one vector. Extra ids are metadata on the same record, not copies.
- **Dedup ANDs all entity ids**: Mem0's conflict-candidate retrieval intersects every entity id passed to `add()`. So `run_id` must NOT be an entity id on writes (it would prevent cross-session dedup); it goes to custom metadata (`kaos_run`) instead.
- **Custom-metadata filtering needs a wildcard**: `filters={"<custom>": v}` alone is rejected; `filters={"user_id": "*", "<custom>": v}` passes validation (Mem0 drops the wildcard, Chroma applies the custom key). This is an undocumented compatibility convention KAOS owns via a pinned version + contract test.
- **`get_all()` is not unfiltered**: it requires at least one entity key; `filters={"user_id": "*"}` is the unfiltered equivalent.
- **Erasure by single key works** over compound records (`delete_all(user_id=…)` removes records that also carry other keys).

## The write/read contract (v2)

- **Writes are provenance, not policy**: every long-term write attaches everything known — entity ids `user_id` + `agent_id`, plus custom metadata `kaos_run` (session) and `kaos_group` (the store's collection name; the old `kaos:group` sentinel is retired).
- **Reads are single-scope filtered**: `user`→`{user_id}`, `agent`→`{agent_id}`, `session`→`{user_id:"*", kaos_run}`, `group`→`{user_id:"*", kaos_group}`. The deliberate semantic change: a `user` read now returns everything the user contributed through any agent/session.
- **Conversational tiers are per-session**: windows and summaries are keyed by the store boundary plus the session id (`kaos_group:<group>|run:<session>`), NOT by the writing agent or principal, so a session's window is addressable at any entitled recall scope while distinct sessions never interleave. Cross-session sharing flows only through extracted long-term facts. (Corrected from the initial "compose all known owners" keying, which over-specified the write with the agent identity — see the conversational-key over-composition bug below.)

## Read-scope policy (#282)

- Agent memory block gains `defaultReadScope` (baseline recall level, default = the agent's `scope`) and `readScopes` (tool entitlement set). `MemoryStore.defaultScope` sets the store-wide default `scope`.
- The explicit tool is ONE `search_memory(query, level)` with the `level` enum **generated from `readScopes`** (unentitled levels never appear in the schema), handler re-validates, owner always server-derived. Chosen over one-tool-per-level after an independent design review: same authority, cheaper token cost, matches Anthropic/OpenAI tool-consolidation guidance; the tradeoff is per-enum-value descriptions are required for routing quality.

## OIDC per-user (#286) and the auth guard (#285)

- **Mode-driven, not presence-driven**: when the cluster has user identity (`SecurityEnabled() && UserIssuer != ""`, injected as `MEMORY_USER_SCOPING=required`), `agent` scope ALWAYS derives `{agent_id, user_id}` and **fails closed** on a missing principal — there is no principal-less partition to leak into. OIDC-off → `{agent_id}` only.
- **Autonomous agents need no exception**: the loop's bearer carries the agent id as principal, so it derives `{agent_id, agent-as-user}` naturally. Consequence (intended): a loop's memory is private to the loop; making findings human-visible is a deliberate `group`-level publication — also the better security posture.
- **The principal bridge**: the gateway emits verified `x-user-claim-sub`, but the runtime read only `x-principal` (a wiring gap the sweep found). `kaos_identity` already had a `PrincipalResolver` hook; #286 registers one reading the claim header. Trust rests on **#285**, which enforces that user auth requires strict gateway routing — so the claim header can only originate at the gateway (verified: Envoy reserves the claim headers, so a client cannot pre-set them).
- Store-level grouping is now a **control-plane choice, not a storage constraint**: `kaos_group` is ordinary metadata, so many-groups-per-store is mechanically possible; one-group-per-store is enforced by convention (group = store binding), leaving finer grouping as an additive follow-up gated on a membership-authorization story.

## Bugs found (unit-guarded fixes + two live-only findings)

Four found by the first live matrix:
- **P4**: conversational keys depended on `Scope.level`, so agent-scoped writes and session-scoped reads produced different keys. First fixed by composing keys from all known owners + session, independent of level — but that over-reached (see the conversational-key over-composition bug below).
- **P5** (live-only): cross-session dedup failed due to a **race** in Mem0's non-atomic search-then-insert across concurrent background extractions — NOT the entity-id hypothesis (that was already correct). Fixed by serializing the consolidation critical section per replica. Unit tests structurally could not catch this; only overlapping live folds did.
- **P7**: conversational keys discarded non-selected attribution, so agent-scoped rows survived user erasure. Fixed by retaining all attribution and deleting on any exact owner token.
- **Recall 500**: user recall with `include_short_term=true` and no session raised an uncaught `ValueError`. Fixed by querying conversational tiers only when a session exists.

Two more found by the final validation and fixed on #286:
- **Autonomous identity**: autonomous/actor contexts preferred a short non-namespaced URI over the operator-injected `AGENT_IDENTITY`. Fixed to use the canonical identity consistently.
- **Incomplete-scope recall**: recall caught owner-resolution errors as long-term outages and returned `200 degraded` instead of failing closed. Now returns **HTTP 400 "incomplete agent scope"** at the boundary. (Confirms the earlier design instinct that a fail-closed refusal must surface as a clean error, not a degraded 200 — the memory service otherwise returns 500 for all errors; 400 here is the deliberate exception.)

One more found at merge time by the committed `example-memory` E2E, after the 17/17 matrix had already passed:
- **Conversational-key over-composition**: the P4 fix folded the writing agent's identity into the conversational key, so a session's short-term window was addressable only at the exact owner-composition it was written with (agent + group), not at a broader recall scope. Writing through a group-scoped agent and then recalling at `group` (no agent supplied) computed a different key and returned an empty window. Fixed by keying conversational tiers on the store boundary + session (`kaos_group:<group>|run:<session>`), with agent and principal excluded; scoped user/agent erasure is preserved via a small session-key→owners index rather than owner segments baked into the key. The te-eval matrix missed it because it always recalled at the same scope it wrote with; the committed example recalls a session's window at a *broader* scope than it was written, which is exactly the mismatch.

## Process learnings

- **Live validation catches what units cannot**: P5 (a concurrency race) and the two final-validation bugs were invisible to unit tests. A cluster matrix with real overlapping operations is not optional for concurrency/identity-sensitive changes.
- **Cluster reuse works and is worth it**: reusing an auth-enabled cluster (keep Keycloak/gateway/AIB/MetalLB/pgvector, `docker stop`/`start` between runs, refresh only operator + CRDs + our images, work in a throwaway namespace) turns ~50 min of setup into ~10. Never `kind delete` a reused shared cluster; delete only the test namespace. A dev Keycloak loses dynamically-registered clients across restart — clear only the stale generated Secrets and let the operator re-register.
- **RAM is the hidden failure mode**: three concurrent KIND clusters starved the Docker VM and turned validation setup from minutes into an hour; `docker stop` of idle clusters (state preserved) unblocked it instantly. Cap live clusters to what the VM can hold; check headroom before launching cluster work.
- **kind cannot rename a cluster** (the name is baked into the control-plane hostname/cert SANs) — a purpose-named reusable cluster must be created with that name from the start.
- **gh-stack (closed beta) handled a real 2-PR stack**: `gh stack rebase` cascaded a rebase onto a moved trunk, pausing per-branch for conflicts; cross-feature operator-controller conflicts had to be *composed* (keep both parameter flows), guarded by the combined operator unit suite. `gh stack push` updates all branches without changing the PR base chain. Auto-submit generates minimal PR metadata — the semantic title/body needs a follow-up `gh pr edit`.
- **The deterministic-mock trap**: a mock model assuming the legacy Mem0 extraction prompt silently wrote no rows; raw Chroma inspection (not the reply text) is the honest assertion surface. Parts of an example that need summarization or model-driven tool routing genuinely need a capable model, not a mock.
- **Committed examples catch what a bespoke matrix misses**: the 17/17 te-eval matrix always recalled at the same scope it wrote with, so it never exercised cross-scope session-window recall and missed the conversational-key over-composition bug. The repo's own committed `example-memory` E2E caught it at merge time precisely because it recalls a session window at a broader scope. Treat the shipped examples as part of the merge gate, not just the custom validation matrix — an example that actually runs is also a regression test with a different bias than the one you designed.
- **gh-stack merges are web-UI-only**: the stacked-PR beta rejects `gh pr merge` and the REST/GraphQL merge APIs on a stacked PR ("must be merged sequentially using the stack merge API"), and the CLI extension has no merge verb — the stack-merge control lives only in the web UI, so a headless session cannot complete it there. Workaround: `gh stack unstack` (full, not `--local`) dissolves the GitHub grouping while leaving all PRs open with their bases and branches intact, then merge bottom-up as normal PRs (`gh pr merge`, `gh pr edit <next> --base main` to retarget, wait CI, repeat). Merge-commits reproduce the exact history the stack intended. Verified on #280→#282→#286.
