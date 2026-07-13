# AIB token-exchange manual evaluation learnings

## Outcome

The delegated third-party path passed on the wire on 2026-07-13 from `feat/kaos-token-exchange` at `991db3b6`. A Keycloak-authenticated user entered the `researcher` Agent, the runtime re-minted the user token for that Agent, AIB ext_proc exchanged it for the user's vaulted mock-provider credential, and the mock API returned HTTP 200. Deleting the vault session caused the next request to return the controlled `third_party_reauth_required` outcome with the authorization URL. An ordinary internal Agent-to-Agent call remained HTTP 200 and never traversed ext_proc.

This was not a clean first-run success. The evaluation found installation wiring defects, a custom-Agent tool registration defect, a permanent runtime deadlock, a PDP mismatch on external routes, and undocumented Keycloak 26 dependencies. The first attempt also exhausted the host by running four KIND clusters at once. The useful result is therefore both the passing flow and the list of conditions required to reproduce it.

## Rig

The final rig used one existing KIND cluster, `kaos-te-eval`, with its control-plane node Ready and Envoy Gateway proxy `2/2`. It ran the KAOS operator and PDP, managed Keycloak 26.0, a self-managed AIB release whose local chart included broker, vault, and ext_proc, one mock OAuth authorization server/API, and four OIDC-DCR Agents: `researcher`, `unbound`, `internal-caller`, and `internal-target`.

The `researcher` used a custom PAIS Agent with two deterministic tools: one called the dedicated mock third-party egress route and one called the internal target. Its model responses were mocked so the evaluation exercised identity, routing, exchange, and policy rather than an external model. The final runtime was built from HEAD as `axsauze/kaos-agent:0.6.1-dev`, layered with the rig's `/app/agent.py`, loaded as `localhost:5001/kaos-te-agent:hangdiag`, and started with `custom_tools=2`.

The `ThirdPartyService` was the real shipped shape: provider `clientID` and `clientSecretRef`, `issuerURI`, explicit authorization/token `endpoints`, declared `scopes`, the protected resource URL, a dedicated `routeRef`, and an `access` binding from `researcher` to scope `read`. The operator projected the service, the Agent permission set, and the sole `EnvoyExtensionPolicy`, `te-eval/github-mock-token-exchange`, targeting only `HTTPRoute/github-mock-egress`.

## The two-exchange chain as proven

The user's normal Keycloak login token decoded as:

```json
{
  "iss": "http://keycloak.keycloak.svc.cluster.local:8080/realms/kaos",
  "sub": "c9df7bbc-c015-4095-b39e-7b5ed1a3f5e9",
  "aud": ["kaos-gateway", "kaos"],
  "azp": "kaos",
  "groups": ["researchers"]
}
```

That token names the login client in `azp`, so AIB cannot use it directly to identify the acting Agent. The runtime performed Keycloak's internal token exchange using the `researcher` DCR credential. The token presented to the AIB exchange path decoded as:

```json
{
  "aud": "token-exchange-broker",
  "azp": "85be1caf-30b9-4236-87b2-fae29613d86d",
  "sub": "c9df7bbc-c015-4095-b39e-7b5ed1a3f5e9",
  "iss": "http://keycloak.keycloak.svc.cluster.local:8080/realms/kaos"
}
```

The `azp`, `sub`, and `aud` assertions all passed. AIB resolved the Agent from that `azp`, checked the real Agent-to-service permission set and the user's grant/vault session, and replaced the outbound authorization credential with the mock provider token. At `2026-07-13T05:20:39Z`, the Agent entry request returned HTTP 200 with `Third-party tool completed.`; Envoy recorded `GET /api/data`, HTTP 200, `response_code_details=via_upstream`, upstream `10.244.0.3:9000`, and 247 response bytes; the mock pod independently logged the same request at the same second.

The important boundary is unchanged: Keycloak performs the user-to-Agent re-mint; AIB performs the Agent-and-user-to-third-party credential exchange. AIB is not the Agent identity issuer, and ext_proc is attached only to the declared external route.

## Bugs found and fixed

| Symptom | Root cause | Fix |
|---|---|---|
| The first AIB Helm install failed because the ext_proc Deployment contained duplicate `EXTPROC_OAUTH2_TOKEN_ENDPOINT` and `EXTPROC_OAUTH2_TLS_ALLOW_HTTP` entries. | The CLI injected environment variables already owned by the chart, so Kubernetes could not construct the typed patch. | `11223b59` (`fix(cli): avoid duplicate extproc environment`), covered by `711d1e1c`. |
| The custom `researcher` Agent started but did not reliably expose the KAOS-added tools. | PAIS appended toolsets to the derived/private `_toolsets` collection instead of the custom Agent's source `_user_toolsets`, so rebuilding the Agent toolset lost the additions. | `840ac013` (`fix(runtime): attach toolsets to custom agents`), covered by `abc88da0`. |
| The first delegated tool request hung permanently with no response or outbound I/O; bounded callers ended as HTTP 000. | The global httpx patch wrapped `AsyncClient.send`. Header injection called `token_async()` to mint/refresh the managed actor token while holding a non-reentrant refresh lock. That mint used httpx, re-entered the patched `send`, attempted header injection again, called `token_async()` again, and waited forever trying to acquire the same lock. In short: patched send -> header injection -> actor-token mint under a non-reentrant lock -> re-entered patch -> deadlock. No HTTP timeout could release it because the code deadlocked before network I/O. | `d94f0946` (`fix(runtime): bypass httpx patch for managed actor-token mint`) adds an instrumentation-suppression context around identity-manager-owned mint requests; `f3d913cb` is the focused reentrancy regression test. |
| The now-valid delegated request reached the generic PDP but was denied before ext_proc. | External `/api/data` has no KAOS `target_resource`, and the re-minted subject intentionally has the broker audience rather than the ordinary internal user audience. The policy only understood entry and internal-resource traffic. | `72026524` (`fix(authz): allow verified delegated egress`) permits only a verified actor plus a verified user-issuer subject with `aud=token-exchange-broker` when no internal target exists; tests retain denial for wrong audiences and for using the delegated token on internal routes. |
| Keycloak returned `unsupported_grant_type`, the shared ext_proc assertion could not satisfy the configured caller check, and fresh installs did not mint the required broker audience. | The dev Keycloak omitted the legacy exchange and fine-grained authorization features; the managed user client lacked the `token-exchange-broker` audience mapper; and AIB CEL compared shared client `kaos` against the per-Agent re-minted token's `azp`, identities that are deliberately different. | `991db3b6` (`fix(cli): align token exchange identity setup`) enables the Keycloak features for token-exchange installs, adds the assertion audience, and validates the configured shared caller identity consistently. Per-client Keycloak exchange authorization remains a deployment dependency described below. |

Two earlier cleanup fixes also remained necessary for the shipped feature: `ea6c5e5b` kept runtime `ty` validation clean, and `36f90089` made removal of an Agent egress binding trigger reconciliation. They predated the manual-evaluation fix range but are part of the final branch.

## Keycloak 26 is a hard dependency, not incidental rig setup

The first direct RFC 8693 probe returned HTTP 400 `unsupported_grant_type`. With Keycloak 26.0, the dev server must start with `--features=token-exchange,admin-fine-grained-authz`; this selects legacy token exchange V1 and the management authorization used to restrict exchange. The KAOS dev installer now supplies those flags only when token exchange is enabled.

Enabling the features was insufficient. The exact `researcher` DCR client then received HTTP 403 `Client not allowed to exchange`. The target client `token-exchange-broker` had to exist, its management permissions had to be enabled, and a client policy/permission had to allow the exact researcher client `85be1caf-30b9-4236-87b2-fae29613d86d` to exchange to it. This per-client permission is mandatory and is not replaced by the AIB permission set.

The target client also needed an audience mapper restricted to `token-exchange-broker`; without it the exchanged token audience is wrong or broader than the contract. A stable subject mapper preserved `sub=c9df7bbc-c015-4095-b39e-7b5ed1a3f5e9`. The final direct Keycloak exchange probe returned HTTP 200 and all three `azp`, `sub`, and `aud` assertions passed.

Restarting the dev Keycloak reset its ephemeral H2 database, rotated JWKS, and invalidated DCR state. Recovery required recreating the target-client configuration and per-client permission, recreating the already-seeded DCR clients with their existing Kubernetes Secrets, and refreshing the PDP JWKS projection from Keycloak's certs endpoint. Production must use persistent state and declaratively manage these permissions and mappers.

The shared ext_proc assertion also requires `aud=token-exchange-broker`. During repair, the live ext_proc was bound to the researcher DCR credential to avoid restarting the seeded in-memory AIB release. Fresh CLI installs instead use the corrected shared-client identity check from `991db3b6`.

## Denial, revocation, and internal invariants

| Check | Status | Wire outcome |
|---|---|---|
| Initial no-consent response | Inconclusive in the first/second attempts | The request hung before exchange because of the httpx reentrancy deadlock, so HTTP 000 was not an authorization result. The rig then completed the real S256 PKCE authorization-code flow, which created the vault session and UserGrant. |
| Successful delegated call after consent | PASS | Agent entry HTTP 200; egress `GET /api/data` HTTP 200; controlled response `Third-party tool completed.` |
| Vault revocation | PASS | Session delete HTTP 200 with `session terminated successfully`; session list HTTP 200 with `sessions=[]`. |
| Retry after revocation | PASS, denied as designed | Agent entry remained HTTP 200 so the application could return the controlled `third_party_reauth_required` outcome. ext_proc received broker HTTP 400 `invalid_grant` and surfaced `/api/third-party/e535ec5d-f544-4403-b044-576c87ab317e/oauth2/authorize`; the third-party tool did not succeed. |
| Wrong delegated audience | PASS in Rego parity | Denied; the delegated-egress rule requires `aud=token-exchange-broker`. |
| Delegated token on an internal route | PASS in Rego parity | Denied; an internal target still requires the ordinary internal subject contract. |
| Live internal Agent-to-Agent call | PASS | Entry HTTP 200, target `GET /health` HTTP 200, response `Internal tool completed.` |
| Internal subject preservation | PASS | The target saw the original user token with `azp=kaos` and `sub=c9df7bbc-c015-4095-b39e-7b5ed1a3f5e9`; it was not replaced by the researcher DCR identity. ext_proc emitted no event for the call. |
| Route-attachment invariant | PASS | The sole `EnvoyExtensionPolicy` targeted `github-mock-egress`; all Agent/internal routes had ordinary `SecurityPolicy` attachments only. |
| Live unbound-Agent denial | Deferred | The earlier fail-fast run stopped before this check, and the final verification concentrated on the money path, revocation, and internal non-interference. Projection and policy tests cover missing bindings, but a distinct live unbound-Agent request was not captured. |

## Infrastructure lessons

The first evaluation started while four KIND clusters were present on the same Docker host: `kaos-aib-spike`, `kaos-authz-doc-validation`, `kaos-manual-e2e`, and `kaos-te-eval`. The new cluster initially reported Ready, then host pressure destabilized the control planes. That run did not establish a product failure. Running one heavy Keycloak+AIB+Envoy rig at a time is a prerequisite for interpretable results; a one-shot health check is not enough when the host is oversubscribed.

The next run reached the application but timed out with HTTP 000. The `researcher` replacement pod then could not become Ready inside a 90-second recovery window because its readiness probe had a 180-second initial delay. The fail-fast stop was correct, but the later code-level reproduction showed that the actual runtime failure was the non-reentrant httpx deadlock, not Kubernetes readiness. Diagnostic timeouts must be longer than configured readiness delays, and an HTTP timeout does not protect against a pre-I/O in-process deadlock.

Dev-state restarts were unusually expensive: both Keycloak and AIB used ephemeral/in-memory storage. Restarting Keycloak erased DCR/permission state and rotated keys; restarting AIB would have erased the seeded vault/grant state. Persistent state is required for a repeatable environment, even if the end-to-end validation remains manual and opt-in.

## Test state

- PAIS: 349 passed, 10 skipped; `ty` reported `All checks passed`.
- CLI: 125 passed.
- Rego parity: 28/28 passed with OPA 1.18.1, including delegated-egress allow and internal-route denial cases.
- Operator `make test-unit`: passed with the repository-required Go 1.26 toolchain; integration suite 45/45 and all packages passed. The host shim initially mixed Go 1.25 with Go 1.26 libraries, so the final run pinned `GOROOT` and `PATH` to Go 1.26.
- All `uv.lock` churn was reverted.

## What remains unproven or deferred

- The third party was a faithful mock OAuth provider/API, not GitHub. Real GitHub endpoint behavior, scope semantics, refresh behavior, and revocation must be validated before calling this GitHub-ready.
- ServiceAccount-primary Agents remain unsupported by this flow because they have no Keycloak client for the re-mint. A secondary Keycloak exchange credential or a different trust design is still required.
- AIB currently resolves the Agent from `subject_token.azp`, while the shared caller is checked independently. The shipped configuration checks the configured shared client identity, but stronger PDP/AIB hardening should cross-check the delegated token's Agent `azp` against the verified actor identity rather than trusting the two validations as separate facts.
- The UI wrapper remains deferred. The raw contract is fail with `third_party_reauth_required` and an authorization URL, complete OAuth, then retry.
- A repeatable opt-in harness was not promoted into the core CI matrix. The manual evidence is passing, but the environment still depends on a local AIB chart and explicit Keycloak 26 target-client permissions.
- A distinct live unbound-Agent denial was not captured in the final verification; unit/projection/Rego coverage exists, but that one wire case remains worth adding to the next manual run.
