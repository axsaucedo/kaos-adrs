# Spike A — a coding harness as an `Agent` flavour, with no new CRD

**Question.** Can a coding harness be deployed as an unmodified KAOS `Agent`, and where is the ceiling?

**Gate: passed.** It deploys and serves end to end with no operator change, and the ceiling turned out to be much higher than the design draft assumed.

## What was built

`driver/harness_driver.py` (~230 lines) wraps `pi` and serves KAOS's existing Agent HTTP surface: `/health`, `/ready`, `/.well-known/agent.json`, `/tools`, `/memory/events`, `/memory/sessions`, `POST /v1/chat/completions` (SSE), and `POST /` (A2A JSON-RPC).

`driver/test_contract.py` asserts conformance against the real consumers in the KAOS codebase, each cited inline. **9/9 pass.**

```
test_liveness_probe                  agent_controller.go:668  /health
test_readiness_probe                 agent_controller.go:681  /ready
test_agent_card_shape                RemoteAgent A2A-support detection
test_chat_completions_non_streaming  kaos agent invoke
test_chat_completions_sse_shape      agent-client.ts:151 + invoke.py:248 heuristic
test_a2a_send_get_list               kaos agent a2a send/get, ListTasks
test_a2a_unknown_method_is_jsonrpc_error
test_memory_events_populated         kaos-ui memory tab, 2s poll
test_parallel_sessions_in_one_pod    the ceiling question
```

`agent-harness.yaml` is a complete harness deployment — git-cloned workspace, hardened `securityContext`, state volume — using **only fields that already exist**. `validate_cr.py` checks it against the committed CRD schema (`operator/config/crd/bases/kaos.tools_agents.yaml`) rather than a cluster, and also checks for silently-pruned unknown fields, since Kubernetes drops rather than rejects those.

```
spec fields used: agentNetwork, config, container, model, modelAPI, podSpec
  present: spec.container.image / spec.podSpec{,.initContainers,.volumes,.containers}
VALID — expressible with no CRD change.
```

## The finding that changes the recommendation

**One pod serves N concurrent, separately-addressable sessions with distinct workspaces.**

```
4 concurrent sessions in one pod in 1.1s; 4 distinct workspaces
```

The design draft argued that `replicas := int32(1)` being a literal with no spec field kills Option A, because "Deployment replicas are fungible and load-balanced, so 'session 3' is not a thing you can route to," and parallel fan-out is the entire point of Mode 2.

**That argument conflates two different things.** One Agent is indeed one pod — but a pod is not one session. The driver keys each session by `X-Session-ID`, gives it its own workspace directory under `/workspace/.sessions/<id>`, and runs its harness subprocess there. Routing to "session 3" is a header, not a Service endpoint. The `replicas` literal is irrelevant to fan-out; it only means fan-out is bounded by one pod's resources instead of spread across nodes.

So the load-bearing objection to Option A does not hold, and Mode 2 — the mode we decided to ship first — is reachable with **zero operator changes**.

## The real ceiling

What Option A genuinely cannot do, in rough order of how much it matters:

1. **No per-session resource limits or isolation.** All sessions share one pod's CPU, memory, and PID namespace. One session running `while true` starves the rest; one session can read another's workspace at `/workspace/.sessions/*`. For a single-operator deployment running one's own tasks this is acceptable; for anything multi-tenant it is not.
2. **Blast radius on restart.** A pod restart kills every in-flight session at once, and KAOS sets no `terminationGracePeriodSeconds`, `preStop` hook, or PDB for agent pods. With per-session pods, one crash costs one session.
3. **Vertical scaling only.** Fan-out is capped by one node's allocatable resources. There is no route to spreading 20 sessions across a cluster.
4. **No session state on the CR.** `AgentStatus` has no task, run, branch, or PR field, so `kubectl get` cannot show what the agent is doing, and any session listing must come from an HTTP call to the pod (the spike added a non-contract `/sessions` route to show what this would need). This is the single biggest UX gap.
5. **No completion semantics.** A `Deployment` never finishes. For a long-lived harness worker serving A2A tasks this is *correct*, not a defect — but it means there is no object whose lifecycle is "this task", and therefore no TTL cleanup and no terminal phase.
6. **`ContainerOverride` is too thin.** It exposes only `image`, `command`, `args`, `env`, `resources`. Everything a coding harness actually needs — `securityContext`, `workingDir`, `volumeMounts` — is reachable only through the full `spec.podSpec` escape hatch. Confirmed against the schema. This is ergonomics, not capability, and is fixable with three fields.

Items 1–3 are all the same underlying thing: **the pod is the isolation unit, and Option A puts many sessions in one pod.** That is the honest axis of comparison against Option C, not parallelism.

## What this implies for design question 2

Option A is sufficient for Mode 2 and costs nothing. The case for a new CRD rests entirely on wanting the *pod* to be the session boundary — which buys isolation, per-session limits, independent failure, horizontal spread, and a status object — and on wanting `kubectl get codingsessions` to be meaningful.

That is a real case, but it is a **second-phase** case, not a prerequisite. A defensible sequence:

- **Phase 1** — harness as an `Agent` flavour. Zero operator change. Ships Mode 2.
- **Phase 1.5** — add `securityContext`, `workingDir`, `volumeMounts` to `ContainerOverride` (small, independently useful).
- **Phase 2** — introduce `CodingSession` only when per-session isolation or a status object is actually wanted, informed by real usage.

The registry question resolves the same way: with one harness and no operator branching on harness type, `kaos-harness-runtimes` would have **no consumer**. Adding it now would repeat the `RequiredEnv` mistake — a field introduced with no code reading it. Defer until a second harness needs operator-side differentiation.

## Not verified

- No cluster deployment. The Docker daemon was down, so the CR was validated against the committed CRD schema rather than applied to KIND. Schema validation proves expressibility, not reconciliation — an envtest or KIND run should confirm the operator actually produces the merged pod spec.
- The driver clones nothing. `_session_workspace` seeds a marker file rather than running `git clone`, so per-session cloning cost and disk growth are unmeasured.
- Delegation was not tested. `DelegationToolset` synthesises `delegate_to_<name>` tools and calls peers over A2A; the driver serves the A2A side but was never used as a *peer* by a real pydantic-ai agent.
- Streaming is coarse: one progress event, then the full final text. Real per-tool-call progress needs `pi --mode json` or `--mode rpc`, which spike D covers.
