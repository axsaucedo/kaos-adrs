# Manual authorization validation learnings

## Outcome

The shipped authorization path was exercised with real HTTP requests and real JWTs on a fresh KIND cluster using Calico v3.32.1. The cluster was named `kaos-manual-e2e`; Calico enforcement was proven before KAOS installation by observing HTTP 200 without isolation and curl exit 28 after applying default-deny ingress.

The headline result is that strict gateway-only mode prevents bypass after the PDP isolation correction found during this run. A protected ModelAPI ClusterIP, a ModelAPI pod IP, an Agent pod IP, and the PDP ClusterIP all timed out from an ordinary workload pod. The same authorized request through Envoy Gateway returned HTTP 200. A valid actor token did not change the off-gateway result because the connection was blocked before policy evaluation.

The consolidated machine-readable result is `tmp/manual-e2e-evidence/status-matrix.json`. Raw headers, bodies, token claim summaries, NetworkPolicies, and operator/broker logs are in `tmp/manual-e2e-evidence/`.

## Flow A: cluster-issued Agent identity

The `kaos-internal` preset with `--gateway-api-strict` was validated through a host port-forward to the real Envoy data-plane Service.

- Autonomous Agent to its granted ModelAPI: HTTP 200.
- The same Agent to an ungranted ModelAPI: HTTP 403.
- Valid actor with no subject: HTTP 403.
- No token: HTTP 403.
- A different valid actor without the target grant: HTTP 403.
- PDP scaled to zero: HTTP 403; after scaling back: HTTP 200.
- Forged signature: HTTP 403.
- Wrong ServiceAccount audience: HTTP 403.
- `alg: none` token: HTTP 403.
- Spoofed `x-kaos-target-resource` claiming the granted resource while requesting the ungranted path: HTTP 403.

This proves the P19 subject requirement, fail-closed PDP behavior, signature/algorithm/audience enforcement, grant enforcement, and path-derived target protection on the wire.

## Flow D: bypass prevention

Calico enforced the generated policies. From `authz-demo/bypass-client`:

- Direct request to `modelapi-granted-model:8000` with a valid actor and subject token: curl exit 28, HTTP 000.
- Direct ModelAPI pod-IP request: curl exit 28, HTTP 000.
- Direct Agent pod-IP request: curl exit 28, HTTP 000.
- Gateway request with the same authorized identity: HTTP 200.

The first direct PDP probe exposed a product gap: `kaos-pdp:9191` accepted the TCP connection in 4 ms because the chart had no PDP NetworkPolicy. The gRPC endpoint was reachable even though curl could not speak its protocol. A chart NetworkPolicy was added, allowing port 9191 only from `envoy-gateway-system`. Repeating the identical probe then timed out with curl exit 28 while the gateway request remained HTTP 200.

## Flow B: Keycloak user plane

An `AccessGrant` for group `researchers` was created before user authentication was configured. It reported `Enforced=False` with reason `NoUserIdentityProvider`. After installing the managed Keycloak user plane it reported `Enforced=True` with reason `Enforced`.

The managed user token contained issuer `http://keycloak.keycloak.svc.cluster.local:8080/realms/kaos`, audiences `kaos` and `kaos-gateway`, a non-empty `sub`, and group `researchers`.

- Group member entering the granted Agent: HTTP 200.
- The same user entering an Agent not covered by its grant: HTTP 403.
- Keycloak token with the wrong audience: HTTP 403.
- Internal hop with a valid OIDC Agent actor and the propagated user token: HTTP 200.
- The same internal actor without the subject token: HTTP 403.

Policy publication and projected ConfigMap mounts were visibly eventually consistent. The first matching request returned 403, then became 200 after several retries within the documented 90-second window.

## Flow C: Keycloak DCR Agent identity

The operator registered one confidential client per Agent through Keycloak DCR and wrote the credentials to `kaos-oidc-<agent>` Secrets. A token obtained with those exact credentials from Keycloak's token endpoint contained `aud=kaos-gateway`; its `azp` exactly matched the `issuer_azp` stored for `kaos://agent/authz-demo/autonomous-researcher`. Using that token as the autonomous actor and subject returned HTTP 200 from the granted ModelAPI.

The DCR bootstrap token must be minted through Keycloak's in-cluster service URL. A token minted through a localhost port-forward contained a localhost issuer/audience and the in-cluster DCR call returned HTTP 401. Minting through `http://keycloak.keycloak.svc.cluster.local:8080` resolved the failure.

Two managed-realm omissions were found. Dynamically registered clients initially received `aud=account`, and the managed user token lacked `sub`. The CLI realm import was corrected to install a realm-default `kaos-agent-audience` client scope for newly registered clients and an explicit user-id-to-`sub` mapper on the managed user client.

## Installation bootstrap finding

The initial `kaos-internal --wait` install stalled because the PDP Deployment mounted `kaos-authz-policy`, but no reconciliation event existed on an empty cluster to create that ConfigMap. Creating the first protected resources triggered projection; deleting the stuck PDP pods allowed the install to complete. The projection controller now enqueues one startup reconciliation so an empty authorization install publishes policy immediately.

## Flow E: AIB best effort — does not work end to end

The available upstream chart was found in `../aib-222-verify/charts/agentic-identity-broker` and the local `agentic-identity-broker:0.1.0` image was loaded into KIND.

The broker first crash-looped because the chart defaults omitted required end-user authentication and its documented base64 key values were decoded once by Kubernetes before the application decoded them again. Supplying pre-auth headers and double-encoded evaluation keys made the broker Running and Ready. These were evaluation-only values.

The KAOS integration still did not reach credential minting:

- The broker returned HTTP 404 from `/.well-known/openid-configuration`, the discovery path used by the KAOS issuer consistency check.
- Agent creation returned HTTP 400: `at least one permission set entry is required`. KAOS intentionally projects identity credentials without AIB authorization permission sets, while this broker version requires at least one.
- The operator reported `credentialsMinted=0`, and both AccessGrants moved to `False/ProjectionFailed` because the combined projection pass failed.
- The available chart did not deploy the upstream ext_proc workload, so its previously observed crash-loop behavior could not be re-tested here.
- Because no Agent credentials were minted, the expected `kaos-gateway` audience on an AIB client-credentials token and an authorized gateway call could not be validated.

This is an integration contract gap, not a hidden test failure. The final running KAOS posture was restored to `oidc-keycloak + gateway-strict`; the healthy AIB broker remains installed only as evidence of the best-effort attempt and is not the selected Agent issuer.

## Product fixes

- `fix(operator): isolate the authorization PDP` adds and tests the PDP ingress NetworkPolicy.
- `fix(operator): initialize authorization policy on startup` eliminates the empty-install policy ConfigMap deadlock.
- `fix(cli): issue gateway audiences for Keycloak identities` adds the DCR Agent audience scope and explicit user subject mapper to the managed realm.

## Deferred

- AIB Agent provisioning needs a contract decision for permission-set-free identity registration or a KAOS-managed placeholder permission model.
- AIB discovery metadata must align with the issuer path consumed by KAOS.
- A chart that actually deploys the upstream ext_proc component is required to reproduce its crash-loop and evaluate the gateway audience interaction.
- The internal user-subject check used the exact runtime wire convention (`Authorization` subject plus `x-agent-authorization` actor) at a downstream ModelAPI. A separate trace-level exercise could additionally demonstrate the runtime automatically copying the inbound user token across a real model/tool call.
