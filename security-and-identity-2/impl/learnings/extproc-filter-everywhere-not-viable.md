# Learning: attaching AIB's ext_proc gateway-wide is not viable for KAOS

## Outcome

Route-scoped ext_proc attachment — the operator attaching AIB's token-exchange filter only to the egress routes it generates for declared third-party services — is **required** for KAOS, not a stylistic preference. Attaching the filter gateway-wide ("filter everywhere, activate selectively", the AgentGateway pattern) is forced out by two facts about the AIB code meeting one fact about KAOS: non-matching resources are denied, not passed through, and KAOS carries a verified bearer token on every hop.

## What the code does

1. **Non-matching resource = deny, not passthrough.** `internal/domain/tokenexchange/service.go:153` documents the exchange error case `InvalidTarget: no service matches resource URI`. A request whose resource URI matches no configured third-party service does not fall through unauthorized — it errors, and the ext_proc server maps that to an `ImmediateResponse` 403.
2. **OPA mode does not change this.** In OPA mode, token exchange still runs first: in the RequestHeaders phase the server calls `s.exchanger.Exchange(ctx, bearerToken, resourceURI)` (`internal/extproc/server/server.go:468`), and only a *successful* exchange proceeds to buffer the body for OPA evaluation. OPA itself runs later, in `processRequestBody` via `s.authorizer.Evaluate(...)` (`internal/extproc/server/server.go:521`), evaluating the already-exchanged request's body. OPA is fine-grained authorization over a successful exchange — which permission-set scopes allow which MCP method/tool — not a "should I touch this request" gate that could pass internal traffic through untouched. The only rego shipped in the AIB repo lives under `tests/e2e/extproc/fixtures/policies/` (`allow_all.rego`, `deny_all.rego`, `allow_readonly.rego`) — e2e test fixtures, not a shipped passthrough policy.
3. **The only passthrough is "no bearer token".** `internal/extproc/server/server.go:339` (FR-009): "No Bearer token — pass through without modification." This is the sole path that skips exchange and OPA entirely.

## Why KAOS's always-bearer rule is the decider

KAOS attaches a verified bearer token to every hop by design — agent to MCP, agent to model, agent to agent. The FR-009 passthrough exists in AIB, but it never fires for KAOS traffic, because KAOS traffic is never bearer-less. Filter-everywhere would therefore route every internal call through `Exchange()` on an internal resource URI. That URI matches no configured third-party service, so every internal call hits `InvalidTarget` and gets a 403. Filter-everywhere would break internal traffic cluster-wide.

This is not a property of AgentGateway being unsuitable, or the proxy being wrong — AgentGateway is not special here. AgentGateway-style demos avoid this failure mode because their internal traffic simply is not bearer-carrying through the AIB filter, so FR-009 passthrough absorbs it. KAOS cannot rely on that escape, because always-bearer is a deliberate KAOS design choice, not an AIB assumption KAOS happens to share. The failure is always-bearer meeting deny-on-no-match; it would reproduce identically in any gateway that both filters everywhere and stamps every hop with a bearer token.

## The simplification is illusory

The operator generates five things per declared third-party service. Filter-everywhere only touches the last one:

| Generated artifact | Purpose | Survives filter-everywhere? |
| --- | --- | --- |
| `Backend` | Egress origin for the third-party service | Yes — still generated |
| `HTTPRoute` | Routes the service's host to its `Backend` | Yes — still generated |
| `SecurityPolicy` (PDP) | Internal authorization decision | Yes — still generated |
| `KAOS_TOKEN_EXCHANGE_CONFIG` | Runtime re-mint targets for the exchanged token | Yes — still generated |
| `EnvoyExtensionPolicy` (ext_proc attach) | Attaches AIB's filter to the route | **Only this changes** — one gateway-wide policy instead of one per generated route |

Filter-everywhere collapses the smallest, best-tested, safest piece of the five — a per-route attachment — into a gateway-wide one. It does not remove any of the other four; the operator still has to compute and reconcile the same service-to-route mapping to build the `Backend`, `HTTPRoute`, `SecurityPolicy`, and token-exchange config. The "simplification" saves nothing on the generation side and only changes how one already-correct policy is scoped.

## Complexity taken on

In exchange for that non-simplification, filter-everywhere requires:

- **An upstream AIB behaviour change**: passthrough-on-no-match, which weakens AIB's own fail-closed posture (`InvalidTarget` today is deliberately a deny).
- **A rego passthrough policy KAOS would author and maintain**, responsible for correctly matching every internal resource URI. This is a denylist-shaped, fail-*open*-if-wrong artifact — exactly the token-leak-onto-internal-routes risk that route-scoped attachment makes structurally impossible today, reintroduced as a policy-correctness problem.
- **A per-request gRPC + OPA cost on all internal traffic**, not just declared third-party egress.
- **A hard runtime dependency of the internal plane on AIB health**, which is zero today — internal traffic does not currently pass through AIB at all.

## Bottom line

Route-scoped ext_proc attachment stays. It is forced by always-bearer plus exchange-denies-on-no-match, not a preference the operator could relax later without reproducing the internal-breakage failure mode filter-everywhere causes today.
