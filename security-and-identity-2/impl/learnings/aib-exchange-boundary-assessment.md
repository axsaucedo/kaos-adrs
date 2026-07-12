# Independent architecture assessment: AIB boundary and exchange mechanics

## Executive conclusion

Adopt option **(b), AIB as exchange only**, with one qualification: treat the current AIB integration as technically plausible but not yet proven for KAOS until a spike validates the subject-token agent binding described below. Keep ServiceAccount or Keycloak DCR as the only primary agent identity mechanisms. Register an agent in AIB only when it declares at least one real third-party service, and project the real service, permission set, AIB agent record, consent, and vault integration needed for that exchange.

Do not preserve an “identity-only AIB” posture and do not manufacture a placeholder permission set. The broker does not model a permission set as an empty registration accessory: an agent request is rejected without one (`../aib-222-verify/internal/adapters/http/handlers/admin/agents_handler.go:476-483`), and a permission set itself must contain at least one real service scope and at least one scope (`../aib-222-verify/internal/domain/storage/permission_set.go:18-49`). A dummy therefore expands into a fake third-party service plus fake scope and creates exchange-shaped state with no exchange meaning. That is operational debt and misleading security data, not compatibility glue.

Option (b) does **not** mean AIB has no representation of an exchange-enabled agent. AIB's consent and exchange domain requires that representation: exchange extracts an AIB agent UUID, loads the agent, and checks the user grant for that principal-agent pair (`../aib-222-verify/internal/domain/tokenexchange/service.go:193-213,229-279`). “Exchange only” means AIB is not the issuer of the agent's internal actor token and does not see agents that cannot exchange; it does not mean agentless exchange.

## 1. Boundary options

### Option (a): AIB identity plus exchange for all agents, with a dummy permission set

This can likely be forced through the registration API, but only by creating more than a nominal placeholder. The handler requires at least one permission-set reference (`agents_handler.go:476-483`), and each referenced permission set requires a service and non-empty OAuth scope (`permission_set.go:18-49`). KAOS would therefore need to own a fake service lifecycle, fake scope semantics, naming and collision rules, pruning, migration, and protection against the fake binding leaking into consent or exchange behavior.

The option's benefit is continuity with the historical AIB issuer adapter and one set of AIB credentials per agent. That benefit is now weak. KAOS has two validated primary issuers: projected ServiceAccount tokens and Keycloak clients registered by DCR. The current AIB projector sends only `display_name` and `description` (`operator/internal/authz/adapters/projector_aib.go:26-31`), and the live test demonstrated that this reduced contract cannot register an agent. Keeping AIB authn would preserve a third issuer, issuer/JWKS configuration, credential lifecycle, chart problems, and failure modes without adding a capability unavailable from SA or DCR.

Assessment: reject. It violates domain truth and disjointness to preserve a redundant issuer path.

### Option (b): AIB exchange only, real bindings only

This gives the cleanest partition:

- KAOS internal identity and authorization: SA or Keycloak DCR actor token, Envoy verification, and the KAOS PDP.
- Delegated external access: AIB service registry, real permission sets, per-user grants, token vault, RFC 8693 endpoint, and egress-only ext_proc.
- Population rule: all agents exist in KAOS; only exchange-enabled agents exist in AIB.

This boundary matches the broker's model. An AIB `Agent` is described in code as an agent that requests delegated third-party permissions and holds `ServiceRequirements` and `PermissionSets` (`../aib-222-verify/internal/domain/storage/agent.go:38-50`). Exchange resolves a protected resource, verifies a principal-agent grant, retrieves a principal-service vault session, and returns that third-party access token (`../aib-222-verify/internal/domain/tokenexchange/service.go:216-327,375-402`). Those are exchange concerns, not internal identity issuance concerns.

The cost is a deliberate dual-registration model for exchange-enabled Keycloak agents: their primary OAuth client lives in Keycloak, while their exchange metadata and real bindings live in AIB. That is acceptable because the two records have different purposes. It is still less state than registering every agent in both systems and inventing fake bindings.

Assessment: preferred, subject to resolving and testing the caller/subject mechanics below.

### Option (c): no AIB; static credentials now and reconsider later

This is the simplest near-term product posture and should remain the default. It does not satisfy the stated future requirement for per-user downstream identity. It is therefore a valid **deferral** option, not a functional replacement. If no committed use case currently needs per-user GitHub identity, defer the exchange implementation while still correcting the ADR boundary now.

## 2. Actual AIB exchange mechanics under option (b)

### Two independent tokens, not one agent actor token

The ext_proc sends two JWTs in the RFC 8693 form: the incoming bearer becomes `subject_token`, while a separately acquired JWT becomes `client_assertion` (`../aib-222-verify/internal/extproc/server/exchanger.go:391-427`). The ext_proc obtains the assertion at startup and refreshes it with an OAuth `client_credentials` grant using its configured client ID and secret (`exchanger.go:505-549`). The exchange endpoint itself does not authenticate the caller from KAOS's `x-agent-authorization` actor token; it validates the form's client assertion and subject token separately (`../aib-222-verify/internal/domain/tokenexchange/service.go:168-208`).

Consequently:

- An exchange-enabled agent must have an **AIB agent record**, because grants, permission sets, and the lookup in exchange use AIB's internal agent UUID.
- The exchange component must hold **OAuth client credentials** capable of obtaining a valid client assertion.
- Those credentials do **not have to be AIB-issued actor credentials**. In the present broker wiring, client assertions are explicitly verified against the upstream OAuth issuer and its JWKS, while subject tokens use the broker-published JWKS (`../aib-222-verify/internal/app/builder.go:831-885`). With Keycloak as the upstream issuer, the assertion is Keycloak-issued.
- A Keycloak-DCR deployment could reuse an agent's Keycloak client credentials in an agent-dedicated ext_proc, or use a separate privileged gateway/exchange client. A shared privileged client is operationally simpler, but then authorization must securely bind that caller and the subject token to the intended AIB agent.
- An SA-primary deployment cannot present its Kubernetes token as the client assertion with the current broker wiring: client-assertion trust is tied to the configured upstream issuer/JWKS (`builder.go:859-885`). It needs a secondary Keycloak/upstream client credential for exchange, or an upstream AIB change adding Kubernetes as an assertion trust policy. This secondary credential is an exchange credential, not the agent's internal identity.

There is a deployment wrinkle. If ext_proc requests its assertion through AIB's proxy `/oauth2/token`, AIB resolves the broker agent UUID and replaces it with that agent record's upstream `client_id` before forwarding (`../aib-222-verify/internal/adapters/http/enduser/oauth2_token.go:76-106`; `../aib-222-verify/internal/adapters/http/enduser/token_grant_strategy.go:52-68`). Alternatively, `client_credentials_endpoint` can point directly to Keycloak (`exchanger.go:505-523`). The ADR must choose one topology and credential owner; “the agent uses its normal actor token” is not what the code does.

### Keycloak subject-token trust is supported, but constrained

Yes, AIB can validate Keycloak-issued subject tokens in its supported proxy/hybrid architecture. The builder constructs separate JWT policies: subject tokens use the broker-published JWKS and accept the upstream issuer (plus the local issuer in hybrid mode), while client assertions use the upstream JWKS and upstream issuer (`../aib-222-verify/internal/app/builder.go:831-885`). Validation checks signature, issuer, the configured broker audience, time validity, and fails closed (`../aib-222-verify/internal/domain/tokenexchange/jwt_validator.go:107-177,287-318`). The expected audience defaults to `token-exchange-broker` and applies to both tokens (`../aib-222-verify/internal/domain/tokenexchange/constants.go:175-188`; `../aib-222-verify/internal/ports/config.go:620-637`).

This is not an arbitrary “trusted issuer” list independent of AIB's OAuth server configuration. The accepted upstream issuer and keys are derived from the broker's configured upstream OAuth issuer and its published/aggregated JWKS. For KAOS, Keycloak must mint the user token with the exact expected issuer and with the AIB exchange audience.

### The main coupling gap: AIB derives the agent from the user token

After validation, AIB extracts both the user principal and the agent identifier from the **subject token**, not from the client assertion. Defaults are `subject_token.sub` and `subject_token.azp` (`../aib-222-verify/internal/domain/tokenexchange/constants.go:138-150`), and the result must resolve to an AIB internal agent UUID before grant lookup (`../aib-222-verify/internal/domain/tokenexchange/service.go:186-208,229-260`). In the common non-multi-agent configuration, the documented expression is `resolveAgentIdByClientId(subject_token.azp)`, backed by AIB's agent `client_id` mapping (`../aib-222-verify/internal/domain/tokenexchange/cel_evaluator.go:29-36,169-203`).

This is the critical unproven point for KAOS. The live KAOS user token is minted for the managed user-facing client and propagated across internal hops. Its `azp` will normally identify that user-facing client, not whichever agent is currently acting. Merely registering each agent through Keycloak DCR does not make an already-issued user token's `azp` change at each hop. Such a token can pass signature validation yet fail agent resolution, resolve the wrong record, or make per-agent consent impossible.

Option (b) therefore works only if KAOS chooses and validates one of these designs:

1. Mint/exchange a Keycloak user subject token specifically for the acting agent so `azp` maps to that agent's AIB record, with `aud=token-exchange-broker` (or the configured equivalent).
2. Add a trustworthy Keycloak-issued custom claim containing the AIB agent UUID and configure `agent_id_expression` to use it. The claim must be set by trusted server-side flow state, not accepted from an arbitrary request parameter.
3. Change AIB so the agent is derived from, or cryptographically bound to, the authenticated client assertion rather than solely from the subject token.

Whichever is selected, the production CEL authorization expression must also bind the privileged caller to the intended operation. AIB's default expression is simply `true` after token validation (`constants.go:148-150`). A shared valid Keycloak assertion plus an independently supplied valid user token is not sufficient caller-agent binding for a multi-agent system.

Therefore option (b) is **architecturally compatible but not yet demonstrated end to end**. The current code does not require the subject issuer to be AIB, and it does not require an AIB-issued caller identity; it does require AIB agent metadata, an upstream-issued assertion, a broker-audience user token, and a reliable agent claim in that user token.

## 3. Keycloak-native exchange instead of AIB

For the deployed Keycloak 26.0 baseline, this is a green-field integration, not a drop-in alternative. Keycloak 26.0 predates supported standard token exchange, which arrived in 26.2; its token exchange was preview. Current Keycloak documentation distinguishes supported standard V2, which handles Keycloak-internal to Keycloak-internal exchange, from legacy V1, where internal-to-external exchange remains preview/deprecated. See [Keycloak's token exchange guide](https://www.keycloak.org/securing-apps/token-exchange) and the [26.2 support announcement](https://www.keycloak.org/2025/05/standard-token-exchange-kc-26-2).

Keycloak identity brokering can store an external IdP token after federated login/account linking and expose it through a broker token endpoint. The documented model is per user and IdP alias, with client/role permission to read the stored token; it is not AIB's per-(user, agent, service) grant model. See the [Keycloak server administration guide](https://www.keycloak.org/docs/latest/server_admin/). Provider scopes are primarily configured on the IdP integration, and KAOS would still need to build the agent-specific consent policy, scope intersection, connection UX, retry/error contract, egress header replacement, refresh/revocation behavior, and operator projection.

The version statement in ADR 0004 also needs updating. As of July 2026, Keycloak 26.6 made JWT Authorization Grant fully supported, and 26.7 made Identity Brokering API V2 supported but disabled by default; the latter adds confidential-client authentication and per-client IdP allowlists. See the [Keycloak release notes](https://www.keycloak.org/docs/latest/release_notes/) and [26.7 announcement](https://www.keycloak.org/2026/07/keycloak-2670-released). These are useful future primitives, but KAOS runs 26.0 and even the newer API still does not supply AIB's triple, consent workflow, service/resource matching, or gateway filter.

Assessment: do not choose Keycloak-native as a “simpler AIB replacement” today. It becomes viable only if KAOS deliberately owns those missing application semantics and upgrades Keycloak. That may eventually be strategically preferable to a young third-party broker, but it is a separate product build and should be compared by prototype, not treated as configuration.

## 4. Recommendation and required ADR changes

1. Select **AIB exchange only**. Delete AIB from the primary `IdentityProvider` choices and keep `serviceaccount | oidc` in `operator/pkg/security/config.go`. Treat exchange as an orthogonal optional capability, not an identity-provider value.
2. Register only exchange-enabled agents in AIB, with a stable KAOS external ID, their relevant upstream Keycloak client mapping where needed, and at least one real permission set covering a real registered third-party service. Never create a dummy service or permission set.
3. Keep static provider credentials as the default and gate AIB exchange. Before adoption, run the proposed KIND spike, expanded to verify exact JWT claims and bindings: ext_proc assertion issuer/audience/subject, user token issuer/audience/`azp` or custom agent claim, AIB agent resolution, caller-agent CEL binding, consent, vault session, successful retry, and revocation.
4. Decide whether ext_proc is per agent, per egress service, or shared. That determines whether Keycloak DCR credentials can be reused or a dedicated privileged exchange client is needed. For SA-primary agents, explicitly provision the secondary exchange credential or change AIB trust; do not imply the SA actor token authenticates AIB.
5. Treat failure to establish a secure agent binding in the spike as a no-go for the current AIB integration, not as a reason to reintroduce AIB as the primary issuer. The fallback remains static credentials while redesigning the exchange contract.

ADR 0002 should remove the claims that AIB authn is a complete standalone retained adapter, that AIB is required when exchange is enabled, and that the three primary issuer choices remain equivalent. The live registration failure and mandatory real permission-set structure falsify the current “identity-only AIB” contract. Replace its AIB boundary with: exchange-enabled agents have an AIB exchange registration; all internal actor identity is SA or OIDC.

ADR 0004 should retain its egress-only, fail/approve/retry, and real-binding direction, but it must stop depending on AIB as the agent issuer. Add explicit sections for the two-token exchange contract, assertion credential ownership, Keycloak upstream trust, required audience, subject-token agent binding, production CEL caller binding, SA-primary behavior, and ext_proc tenancy. Correct the Keycloak maturity statement to distinguish the deployed 26.0 baseline from current releases.

The unresolved design decisions are therefore concrete: how a propagated user token securely names the acting agent; whether the exchange caller is per-agent or shared; who owns and rotates its Keycloak credentials; how an SA-primary agent obtains a compatible exchange assertion; and whether AIB's chart/deployment gaps are acceptable. None of these justifies dummy state or retaining AIB as a redundant internal identity issuer.
