# Python SDK and header propagation — implementation plan

**Branch (KAOS)**: `feat/p1-sdk-propagation`, stacked off the P0 base; PR #232
**Tracking issue**: axsaucedo/kaos#231

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change -> validate tests pass -> commit (comprehensive, functional message describing WHAT changed; NO phase/task/ADR references in messages, branches, code comments, or PR text) with Copilot co-author.
- Push to the PR and validate CI green. Run python tests locally; prefer the full suite in CI; be efficient with testing. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored), noise -> `./tmp/null`. End: gitignored REPORT.md (all prior + current tasks), posted as a PR comment (not committed).

## Problem statement

Deliver the first atomic component: two-identity header propagation as a reusable library in the KAOS python repo (temporary home, for easy import/iteration). Outbound calls from the `pais` runtime (RemoteAgent / MCP / A2A hops) must forward the user subject and attach the agent actor, so the identity of both the originating user and the acting agent travels across hops. Identities are dummy/static at this stage — real minting and machine-token lifecycle come later — and no access-check/enforcement is built here.

## Current-state grounding (researched)

- `pais` makes outbound calls via `httpx` from RemoteAgent (A2A/chat delegation), MCP tool calls, and sub-agent delegation; there is no shared request-scoped identity context today.
- P0 validated the propagation shape end-to-end (`30-propagation.py`): user subject forwarded, agent actor attached, request-id carried, per-hop actor override.
- ADR-AIB-001 (propagation slice) and ADR-KAOS-003 (user-request context propagation) define the header contract this realises.

## Design plan (how it fits)

Introduce a request-local security context that holds the inbound user subject and the agent's actor identity, populated from incoming request headers and propagated automatically onto every outbound `httpx` call the runtime makes. Wire the context through the runtime's outbound paths (RemoteAgent, MCP, A2A) so a chain A→B→MCP carries both identity headers correctly across each hop. Keep identities static/dummy for now behind the same interface that real minting will later implement, so downstream phases swap the source without touching call sites.

## Numbered TODOs

1. **Request-local security context + header propagation.** Add a request-scoped security context and an `httpx` hook that injects the propagation headers (user subject + agent actor + request-id) on outbound calls. **Validate**: unit tests for context population and header injection; `pytest` + `make lint`.
2. **Inject propagation headers on outbound httpx calls.** Apply the propagation hook across the runtime's outbound client(s) so all hops carry the headers. **Validate**: unit tests asserting headers present on outbound requests.
3. **Propagate user and agent identities through the runtime.** Thread the user subject and agent actor through RemoteAgent / MCP / A2A outbound paths, with per-hop actor override. **Validate**: unit tests for per-path propagation.
4. **Cross-hop propagation test.** Verify two-identity propagation across agent hops (A→B→MCP) end-to-end. **Validate**: `pytest` propagation test green.
5. **Document the SDK.** Document the identity propagation SDK in the python instructions/docs (header contract, static-identity caveat, no enforcement yet). **Validate**: docs build / review; no functional change.

## Validation per task

Per-TODO targeted `pytest` + `make lint`/black in `pydantic-ai-server`; push the PR and confirm `python-tests` CI green. No e2e or enforcement is exercised at this phase.

## Commit / PR strategy

- `feat/p1-sdk-propagation` stacked on the P0 base; one comprehensive commit per TODO; PR #232; keep CI green; Copilot co-author trailer on KAOS commits.
- REPORT.md gitignored; contents as a PR comment.

## Out of scope (later phases)

Real actor-token minting and machine-token lifecycle; access-check helpers/enforcement (P2 gateway `ext_authz`); install + sync wiring (P3); SDK productionisation — retry/caching/observability and `external_id` minting (P9); `ext_proc` token exchange (P7).
