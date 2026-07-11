# Research 004 — The Keycloak + KAOS-run OPA authorization path (Option 2 target)

**Date**: 2026-07-11
**Sources**: phase-1 [ADR 0001](../../security-and-identity/adrs/adr_0001_enforcement-topology-and-policy-engine.md) (the retained ext_authz seam), [model-parity learnings](../../security-and-identity/impl/learnings/opa-extproc-authz-model-parity-and-oauth-path.md), Envoy Gateway `SecurityPolicy` behavior verified in the live P13–P17 work, and research/001–003 in this folder.

This document assembles the facts that make Option 2's authorization half concrete: **a KAOS-deployed OPA answering Envoy `ext_authz`, fed by Keycloak-verified subject claims, broker-verified (or alternative-issuer) actor claims, and KAOS-projected grant data.** It records why this path is viable, what carries over from phase 1, and what is genuinely new.

## Why ext_authz + KAOS-run OPA is structurally different from what failed

The phase-1 failure was not "OPA at the gateway" — it was *whose* OPA and *inside which filter*. AIB's OPA runs inside its token-exchange ext_proc, giving KAOS no control over the evaluate-vs-exchange coupling or the no-bearer bypass. A KAOS-run OPA behind `ext_authz` inverts every blocker from research/001:

- **No exchange coupling** — ext_authz is a pure check: the filter asks "allow?" and forwards the original request untouched on allow. "Authorized but not exchanged" is the *only* mode, not an inexpressible one.
- **Runs unconditionally** — the ext_authz filter evaluates every request on the route, bearer or not. The G1 autonomous bypass becomes closable by construction: "no subject token" arrives at the policy as a fact to reason about, not a branch that skips evaluation.
- **KAOS owns the deployment** — policy enablement, rego content, data mounting, and upgrade cadence are all KAOS chart concerns; no off-by-default upstream config or chart surgery (the deployment blockers in research/001 simply don't apply).
- **First-party Envoy Gateway support** — `SecurityPolicy.spec.extAuth` (gRPC or HTTP) is a stable Envoy Gateway API, and phase-1 ADR 0001 deliberately retained an optional, default-off ext_authz seam in the KAOS chart precisely so a decision service could be swapped in later. Option 2 promotes that seam from escape hatch to primary decision point.
- **Proven shape** — OPA's `envoy_ext_authz_grpc` plugin (`envoy.service.auth.v3.Authorization`) is the standard, widely deployed way to run OPA as an ext_authz backend; the fork's access-check gRPC server implements this same protocol, confirming the pattern fits the AIB-adjacent domain.

## What carries over from phase 1 unchanged

- **Identity plumbing** — gateway `jwt_authn` with two providers (`user` → Keycloak JWKS on `Authorization`, `agent` → broker/issuer JWKS on `x-agent-authorization`) already verifies both tokens before any authz filter runs; verified claims can be forwarded to the policy.
- **Resource identity stamping** — `x-kaos-target-resource: kaos://<slug>/<ns>/<name>` header per route.
- **The projection pipeline** — `AuthzProjectionReconciler`, the policy ConfigMap (`policy.rego` + `data.json`), the automated/manual/operator-rego modes, and the safety rule that KAOS never prunes data it doesn't own. Only the *consumer* of the ConfigMap changes (a KAOS-run OPA container instead of AIB's ext_proc), plus a schema extension for the user dimension (research/003).
- **The published `data.kaos.*` contract** — extended, not replaced; existing `grants` and `jwks` keys keep their meaning.
- **Presets** — `kaos-internal` / `aib-only` / `aib-keycloak` remain the CLI surface; their internals re-map onto the new topology (which enforcement filter is installed, which issuer backs the `agent` provider).

## What is genuinely new (the ADR work)

- **The OPA deployment shape** — sidecar-vs-standalone Deployment, gRPC vs HTTP ext_authz, failure mode (Envoy's ext_authz `failOpen` must be false), ConfigMap hot-reload (OPA bundle polling vs mount-propagation; phase-1 F4 noted kubelet sync delay up to ~90s).
- **Claim forwarding into the policy input** — deciding how verified subject/actor claims reach OPA: ext_authz receives the raw headers (OPA can decode/verify JWTs itself against `data.kaos.jwks`, as the current rego does), or `jwt_authn` claim-to-header forwarding (`claimToHeaders`) hands pre-verified claims over. Double-verification vs trust-the-filter is a real decision with performance and spoofing-surface implications.
- **The user dimension** — schema and rego conjunction per research/003, including the autonomous "no subject" stance per posture.
- **Keycloak as user-fact source** — realm/client role and group conventions for user→agent authorization, and whether KAOS's Keycloak install (the `aib-keycloak` preset already provisions it) should pre-create the client scopes/mappers that surface those claims.
- **Filter ordering and coexistence** — ext_authz must run after `jwt_authn`; if AIB's ext_proc remains deployed for future exchange/consent work (F9), the two filters coexist and ordering/responsibility must be pinned down — or ext_proc is dropped from the enforcement path entirely (interacts with the F0 chart gaps noted in research/002).

## Fit against the option-2 goal

| Requirement (from the phase-2 framing) | This path |
|---|---|
| Agent authn via AIB, no token exchange | Untouched — research/002 surface is orthogonal to the authz filter |
| Authorization from Keycloak | Subject claims (roles/groups) verified at the gateway, evaluated in KAOS-run OPA |
| With OPA | KAOS-deployed OPA, KAOS-owned rego + data, published contract retained |
| USER + Agent + Resource | Expressible: all three fact sources reach one policy input; conjunction is a rego/data change |
| Close G1 | ext_authz evaluates unconditionally; "no subject" becomes policy-visible |
| No fork, no upstream dependency | OPA is upstream CNCF; AIB is used only through its stable authn/admin APIs |

The open decisions above are exactly the ADR set proposed in [adr_high_level_components](../adrs/adr_high_level_components.md).
