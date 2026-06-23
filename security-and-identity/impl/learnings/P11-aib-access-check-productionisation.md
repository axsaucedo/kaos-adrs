# P11 — AIB access-check API productionisation (learnings)

## Reuse the broker's existing user-token authenticator for the subject — do not extend the actor validator

The actor token and the user (subject) token are different credentials with different issuers/audiences. The access-check already had an `ActorTokenValidator` over the broker's published JWKS; the temptation is to thread the subject through the same validator. That is wrong. The broker already has a user-token `JWTAuthenticator` (the one `RequirePrincipalMiddleware` uses); the subject path reuses it verbatim. Keeping the two validators distinct is what enforces the actor/subject separation at the type level: the actor validator yields an `AgentID` that drives the decision, the subject validator yields a principal that is recorded only. A `UserGrant` must never grant resource access (FR-010), and using separate validators makes that hard to violate by accident.

## Fail closed at the *decision* layer, not with a 500

The original P2 handler returned HTTP 500 when the decider errored (repo failure, etc.). For a gateway-facing authorization API, a 500 is ambiguous and can be read as a transient blip rather than a denial. The productionised handler instead converts decider/timeout errors into a `200 {allowed:false}` decision with a specific reason (`internal_error`, `deadline_exceeded`) — the request was well-formed, so the HTTP status reflects request validity while the body fails closed. This makes "the broker had a problem" indistinguishable-by-default from "denied", which is the safe posture for an authz check. The 4xx codes are reserved for request-layer problems (malformed body, missing resource, unauthenticated/unauthorized caller).

## Caller authorization is a request-layer concern, separate from the decision

There are two trust questions on this API: "is the *caller* allowed to ask for decisions?" (FR-005) and "is the *actor* allowed to reach the resource?" (the decision). They must not be conflated. The caller check lives in routing middleware (`RequirePrincipalMiddleware` + an allowed-caller set) and rejects with 401/403 before the handler runs; the actor decision is the 200 body. The gRPC surface's caller is the gateway at a trusted network boundary, so it is authorized structurally rather than per-request. The HTTP caller check is config-gated so dev/no-auth installs still work — but it fails closed when enabled with an empty allowed set.

## Ambiguous resource resolution is a distinct fail-closed case

Mapping a `kaos://` resource URI to a synthetic service can fail two ways: no match (not-found) or more than one match (conflict). Only modelling not-found leaves the ambiguous case to fall through as an allow or an error. The resolver now surfaces a conflict distinctly and the domain maps it to a dedicated `resource_ambiguous` deny. Completing the fail-closed set (missing/invalid actor, malformed actor/subject, missing resource, ambiguous resource, repo errors, deadline) is the bulk of the "production bar" for an authz check.

## The AIB Dockerfile packages a pre-built binary — build the binary first

The broker `Dockerfile` does `COPY ./bin/linux/${TARGETARCH}/agentic-identity-broker` rather than compiling inside the image. A plain `docker build` therefore packages whatever stale binary is already in `./bin/` (and completes in ~0.1s, which is the tell). For a KIND smoke against new code you must run `just build-linux-arm64` (or the matching arch target) *before* `docker build`, then `kind load` and restart the deployment. This bit the first smoke attempt: the in-cluster response was missing the new `decision_id`/`message` fields purely because the image carried the old binary, not because of a code bug.

## helm upgrade --reuse-values pins the image tag

`helm upgrade ... --set image.tag=<new> --reuse-values` did not move the running image off the previous tag, because the previously-merged values won. For an iterative KIND loop, set the image directly (`kubectl set image`) or drop `--reuse-values`, then verify the pod's `spec.containers[0].image` actually changed before testing.

## Redaction is verifiable, so verify it

Token redaction is easy to claim and easy to get wrong (a stray `err.Error()` or a logged request body re-introduces the secret). The cheap, decisive check is to feed a recognizable sentinel token through the path and assert it appears zero times in logs/traces/error output — done both as a unit test and as an in-cluster `kubectl logs | grep -c <sentinel>` smoke. Both returned zero here.

## Additive contract, unchanged shape

Every new response field (`principal`, `decision_id`, `matched_grant`, `message`) is additive; existing P2 behaviour (actor-keyed allow/deny, fail-closed, resource mapping) stays green throughout. The first-class resource-grant model is evaluated as a design note rather than implemented, precisely so the API contract does not change when the internals later swap from bootstrap lookup to native grants. Keeping the contract stable now is what makes that future swap a non-event for callers.
