# Research 002 — AIB's agent-authentication surface (the Option 2 subset)

**Date**: 2026-07-11
**Sources**: codebase inspection of the local `agentic-identity-broker` clone with file presence verified against `upstream/main` (all authn-surface files listed below exist upstream, predating the fork divergence at `#396`); phase-1 learnings ([aib-ext-proc-limitations](../../security-and-identity/impl/learnings/aib-ext-proc-limitations.md), [followups F0/F2](../../security-and-identity/plan/followups.md)); the working KAOS integration on PR `axsaucedo/kaos#267`.

This document scopes **exactly what AIB provides for agent authentication independent of ext_proc and token exchange** — the subset Option 2 keeps. Conclusion: the subset is complete, standalone, proven working in the live KAOS deployment, and needs none of the exchange machinery.

## The standalone authn surface (all on upstream `main`)

- **JWKS discovery** — `GET /oauth2/jwks.json` (`internal/adapters/http/handlers/enduser/jwks_handler.go:40-64`). Public, no credentials, `Cache-Control: max-age=300`. This is what the gateway `agent` JWT provider and the KAOS `data.kaos.jwks` injection consume.
- **Agent registration (admin API)** — `POST /api/agents`, `GET/PUT /api/agents/{id}` (`internal/adapters/http/handlers/admin/agents_handler.go:121-325`). The KAOS operator's projection controller already drives this.
- **Client-credentials lifecycle (admin API)** — `POST /api/agents/{id}/client-credentials` mints or rotates (secret returned once), `GET` returns metadata only, `DELETE` revokes (`internal/adapters/http/handlers/admin/client_credentials_handler.go:57-210`). The operator mints per-agent credentials into Secrets through this today.
- **Token minting** — `POST /oauth2/token` with `grant_type=client_credentials` (`internal/adapters/http/enduser/oauth2_token.go`). Dispatch is by client type (`token_grant_strategy.go:29-42`): agents with neither upstream `ClientID` nor `ClientURIs` are **LocalClients** (`internal/domain/storage/agent.go`, `ClientType()`), for which the broker mints the token locally — no upstream IdP round-trip. KAOS agents are LocalClients, which is why `aib-only` works without Keycloak.

None of these paths touch the exchanger, the vault, consent, or ext_proc. Dropping token exchange from the KAOS integration removes zero authn capability.

## What KAOS already has wired against this surface

- **Operator projection** registers agents, binds permission sets, and mints credentials (phase-1 [ADR 0004](../../security-and-identity/adrs/adr_0004_component-architecture-and-projection.md)); the projection reconciler is the sole AIB caller.
- **Runtime token client** — vendored at `pydantic-ai-server/aib/identity.py`, provider-agnostic (any token endpoint + client id/secret). Agents obtain their actor token and send it in `x-agent-authorization`. Folding it into the KAOS Python SDK is followup F2.
- **Gateway verification** — the resource `SecurityPolicy` carries an `agent` JWT provider validating `x-agent-authorization` against the broker JWKS, alongside the `user` Keycloak provider. Live-demonstrated in phase 1: token presence/validity is enforced with specific `401` reasons, and the actor token `sub` equals the logical identity `kaos://agent/<namespace>/<name>`.

So the "AIB for agent authn" half of Option 2 is not a proposal — it is the part of phase 1 that **worked** and was demonstrated end to end.

## Known sharp edges to carry into the design

- **Issuer/public-URL mismatch (fixed KAOS-side, fragile)** — the broker defaults `server.enduser.public_url` to `http://localhost:8000` (`internal/ports/config.go:185`) and stamps it as token `iss`; mismatched `iss` fails gateway verification with `Jwt_issuer_is_not_configured`. KAOS now sets `broker.server.enduser.publicUrl` at install time (PR #267 commit `68da2ea2`), but there is no render-time assertion; F0 tracks folding this into a consistent mechanism.
- **Chart env gaps (F0)** — the AIB chart cannot set `EXTPROC_OAUTH2_CLIENT_CREDENTIALS_ENDPOINT` or arbitrary env; KAOS patches post-install. Under Option 2 the ext_proc sidecar may not be deployed at all, which would delete this problem rather than fix it — a point the topology ADR must settle.
- **Token-exchange CEL authorization exists but is separate** — the broker's `/oauth2/token` RFC 8693 path has an optional CEL check (`internal/ports/config.go:672-726`); irrelevant if exchange is excluded, but it must not be mistaken for a `client_credentials` authz gate (there is none — possession of credentials is the only control on minting).
- **G1 interaction** — under the current gateway wiring, an agent-token-only request (no user bearer) passes `jwt_authn` and then hits ext_proc's no-bearer `passThrough()`. Authentication holds; nothing authorizes. Option 2's KAOS-run OPA must cover this path (see [research/004](./004-keycloak-and-kaos-run-opa-authz-path.md)).

## Alternatives to AIB for the same subset (recorded for the ADR options)

Phase-1 followup F1 already sketched the AIB-less issuers; they become first-class options in the new identity ADR:

- **Keycloak client-per-agent** — reuse the user IdP as the agent trust anchor; requires a Keycloak-sync analogue of the AIB credential mint and issuer/JWKS wiring. One fewer deployed system in the `aib-keycloak` posture; loses AIB's agent-centric admin model and the future consent/vault path (F9).
- **Kubernetes projected ServiceAccount tokens** — most Kubernetes-native, no external issuer at all; the SA `sub` is not `kaos://agent/...` so identity mapping moves into policy data; audience/rotation need design.

Keeping AIB for authn preserves the only credible path to its differentiating capability — consent-based delegated third-party access (F9) — without paying for the exchange machinery now.
