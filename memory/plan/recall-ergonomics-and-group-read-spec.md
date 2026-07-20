# Working spec: recall ergonomics and group-read control (DRAFT, not finalised)

Status: parked pending final review. Implementation explicitly on hold; do not start executors on this until approved. The Codex brief for the ergonomics half exists at `kaos/tmp/brief-recall-ergonomics.md` and matches the decided section below.

## Decided (requested renames and CLI ergonomics)

1. Recall response keys become self-describing and flat: `facts` -> `long_term_facts`; `medium_term.summary` -> `medium_term_summary` (string); `short_term.recent` -> `short_term_window` (list of [role, content]). `block` and `degraded` keep their names. A tier's key is present only when requested.
2. Tier selection through one option: `--include` accepting `a|all|s|short-term|m|medium-term|l|long-term`, repeatable and comma-splitting, defaulting to `all`. Wire: `include: [...]` list replaces `include_short_term`; the service fetches only requested tiers (short and medium share the conversational store, so selective fetch is two queries on one backend).
3. Query optional: `--query` present means semantic recall (`/v1/recall`); absent means list (`/v1/list`). `--all` and `--short-term` flags are removed. `--query` without long-term in `--include` is an error.
4. The automatic baseline recall in the runtime keeps requesting all tiers; agent behaviour unchanged.

## Open questions (to resolve before finalising)

1. **Group-level read semantics.** Since scoping v2, group recall filters only on the store's `kaos_group` tag, which every record carries, so `group` reads return the entire store including facts extracted from every user's private conversations. Any agent whose author lists `group` in `readScopes` exposes that to the model, letting one user surface another user's extracted facts. Options: (a) keep group as the whole-store admin/audit view and gate it (see 2); (b) reintroduce deliberate group ownership as in ADR 0005 v1 (a publication partition such as the reserved `kaos:shared` owner, written to intentionally), making group reads safe; (c) both.
2. **Store-level read ceiling.** Proposed `MemoryStore.spec.allowedReadScopes` capping what bound agents may be entitled to, enforced at operator reconcile (reject exceeding agents) and authoritatively at the service read path (projected `KAOS_MEMORY_*` env). Neither enforcement exists today: `readScopes` is enforced only client-side (tool schema enum plus runtime check); the service checks owner-key completeness only. Decide the default (proposal: `[session, agent, user]`, group opt-in) and whether the ceiling also binds the admin plane.
3. **Per-user consent for cross-agent sharing.** `user`-level reads move a user's own facts across agent boundaries; the consent boundary today is store membership, which is operator-shaped with no user opt-out. Decide whether a consent knob is in scope or explicitly deferred.
4. **Worked-example rework.** Replace the fabricated `support-team-publisher` direct write with bob writing through the agent (bob logs in, raises a ticket, mutual isolation shown: alice's recall lacks bob's facts and the reverse; forget stops at the principal). Decide the fate of the group-recall segment (drop, or reframe as the admin whole-store view). Needs a targeted re-capture.
5. **Sample AccessGrant subjects.** The identity group `researchers` in the sample's grant collides conceptually with the memory store group. Consider granting `kind: User` subjects (alice, bob) instead for the example's clarity.
6. **Possible `kaos memory write` admin command** for legitimately seeding shared knowledge with explicit attribution, if option (b) in question 1 is taken.

## Terminology note

Two unrelated "groups" exist and must never be conflated in docs: identity groups (token `groups` claim, AccessGrant entry authorization) and the memory store group (`kaos_group`, one per store, "the store is the group").
