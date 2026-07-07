# Actor-token `sub` must equal the KAOS logical identity — runtime verification (pending live broker)

**Status**: Design assumption locked into code; runtime verification against a live broker still outstanding. This note records the assumption, why it matters, exactly where the code depends on it, and how to verify it so the check is not lost.

## The assumption

The Model-1 authorization data path keys grants by the **actor identity** carried in the `x-agent-authorization` token's `sub` claim. The operator projects grants as `data.kaos.grants[<actor_sub>] = [<resource logical ids>]`, where it assumes `<actor_sub>` is the KAOS logical identity `kaos://agent/<ns>/<name>` (the agent's `ExternalID`, which is also `AGENT_AUTH_IDENTITY` in the runtime). The static policy reads the actor `sub` from the token and looks it up directly in `data.kaos.grants`. If the broker instead stamps `sub` as an internal opaque UUID (its own primary key for the registered agent), every lookup misses and the policy denies every request even for correctly granted edges.

## Why it matters

This is the single load-bearing identity join across the whole Model-1 chain:

- Operator registers the agent at the broker admin API and derives its grant-map key from the CRD logical identity.
- Runtime mints the actor token via `client_credentials` (`aib/identity.py`), with `AGENT_AUTH_IDENTITY = kaos://agent/<ns>/<name>`.
- Gateway ext_proc invokes OPA; the policy trusts the token `sub` and matches it against the operator-projected key.

The projection side and the token side must agree on the exact string. The projection uses the logical identity; the token `sub` is whatever the broker chooses to put there. Only a live broker mint proves they match.

## Where the code depends on it

- Grant emission keys on the agent `ExternalID` (`kaos://agent/<ns>/<name>`): `operator/internal/projection` grant-data emitter.
- The policy reads `input.attributes.request.http.headers["x-agent-authorization"]`, decodes it, and looks up `data.kaos.grants[actor_sub]`: `operator/internal/authz/policy.rego`.
- Runtime mint sets the client-credentials subject to the logical identity: `pydantic-ai-server/aib/identity.py` (`AGENT_AUTH_IDENTITY`).

## How to verify (do not assume)

1. Deploy the broker (AIB `main` incl. #222, plus #397 deployability) into a KIND cluster and register an agent via the operator projection.
2. Mint a `client_credentials` token for that agent (the runtime path, or a direct `POST <issuer>/oauth2/token`).
3. Decode the token and inspect `sub`.
   - **If `sub == kaos://agent/<ns>/<name>`**: assumption holds, no code change.
   - **If `sub` is an internal UUID**: either (a) key the Model-1 data by that UUID (project the broker's returned agent id into the grant-map key), or (b) carry a `data.kaos.uuid_to_logical` map in the data document and resolve the logical id in the policy before the grant lookup.

## Recommended next step

Fold this into the local KIND enforcement e2e (allow/deny via ext_proc OPA): the same run that mints the actor token and drives a granted vs ungranted call is where the `sub` value should be asserted, so the assumption is verified and regression-guarded in one place.
