# Manual end-to-end validation (final CLI-preset posture pass)

This is the final manual validation pass tied to the CLI simplification. Its purpose is to confirm that the two supported install postures selected by the single `--auth-enabled` flag produce a correct end-to-end wiring, and to record what was validated live versus what remains a Calico/broker-gated follow-up. It builds directly on the earlier `manual-e2e-P6-P10-validation.md` and `opa-extproc-authz-model-parity-and-oauth-path.md` learnings.

## Supported postures under validation

The install command now exposes two curated postures instead of ~26 fine-grained flags:

- **`kaos-internal`** — self-contained demo, no external identity provider or broker. The `kaos` provider projects the grant graph from CRDs into a policy ConfigMap enforced by OPA in the gateway `ext_proc` filter. The agent (actor) JWT is header-trusted (`agentJwtVerification=skip`), which is spoofable and explicitly non-production. Internal traffic is gateway-routed and bypass-prevention NetworkPolicies are generated.
- **`aib-keycloak`** (default) — full verified path. Keycloak provides user identity, the identity broker provides agent identity and RFC 8693 token exchange, and authorization reads the broker permission sets with the actor JWT signature verified against the IdP JWKS.

Both imply `--gateway-enabled`. The granular flags are retained as hidden advanced options so the E2E harness and power-user compositions are unaffected.

## What was validated

### CLI preset expansion (unit)

The preset expander maps each posture onto the underlying install parameters, asserted by the CLI integration suite: `kaos-internal` yields provider `kaos`, `ext_proc` extension, `agentJwtVerification=skip`, automated projection, user-auth and token-exchange off; `aib-keycloak` yields provider `aib`, verified JWT, user-auth and token-exchange on. The `--auth-enabled` flag with no value defaults to `aib-keycloak` (same preprocessing used by `--monitoring-enabled`), an unknown value is rejected, and both presets imply `--gateway-enabled`. Standalone `--gateway-api-strict` emits the strict value with no auth wiring. Full suite green (105 tests).

### Chart wiring (render)

Rendering the operator chart with the exact `--set` values the demo preset produces emits the expected operator config: `SECURITY_AUTHORIZATION_PROVIDER=kaos`, `SECURITY_AUTHORIZATION_GATEWAY_EXTENSION=ext_proc`, `SECURITY_AUTHORIZATION_AGENT_JWT_VERIFICATION=skip`, `SECURITY_AUTHORIZATION_POLICY_DATA_SOURCE=automated`, and `SECURITY_GATEWAY_ROUTING_ENABLED=true`. This confirms the CLI → chart contract is correct for the demo posture. The operator's own projection e2e (`operator/tests/e2e/test_authz_policy_projection_e2e.py`) covers that these env values make the operator render the static rego plus a grant graph into the policy ConfigMap and keep grants stable across reconciles.

## What remains a follow-up (deferred, tracked)

- **Live NetworkPolicy strict enforcement.** The available local cluster uses kindnet, which does not enforce `NetworkPolicy`. Proving that the generated policies actually block the direct ClusterIP bypass (the TEST A / TEST B pair in `manual-e2e-P6-P10-validation.md`) requires recreating the cluster with a NetworkPolicy-enforcing CNI (Calico, `disableDefaultCNI: true`). This is a Calico-gated manual check, not runnable in kindnet CI.
- **Full `aib-keycloak` soup-to-nuts allow/deny walkthrough.** A single reproducible bring-up that installs Keycloak, the identity broker (with the ext_proc token-exchange component and an OPA authorization policy that reads `granted_permission_sets`), registers agents, mints actor tokens, and demonstrates a user-present allow next to a denied edge is not yet automated. The components were validated piecewise in their own phases; the missing piece is the install automation that also enables AIB's ext_proc OPA authorization decision (not just the token-exchange path) and mounts a rego, plus a live allow/deny assertion.
- **Autonomous no-bearer gap (G1).** OPA in `ext_proc` only evaluates when a subject bearer token is present; pure-autonomous agent-to-resource calls with no user token bypass the policy. This is an upstream `ext_proc` constraint to document rather than fix here.

## Recommended reproducible bring-up (for the deferred live pass)

```bash
# Demo posture — no external IdP/broker, functional allow/deny via KAOS-owned policy
kaos system install --gateway-enabled --metallb-enabled \
  --auth-enabled kaos-internal --chart-path operator/chart --wait

# Full verified posture — requires the (unpublished) broker chart path
kaos system install --gateway-enabled --metallb-enabled \
  --auth-enabled aib-keycloak \
  --aib-chart-path <path-to-aib-chart> --aib-values <dev-preset-values> \
  --chart-path operator/chart --wait
```

The demo posture is the recommended first live target: it needs no external identity provider or broker and exercises the full KAOS-owned authorization path. The verified posture should follow once the broker install also enables AIB's ext_proc OPA authorization decision, so a valid-token allow and a denied edge are both reachable on the real gateway-routed path.
