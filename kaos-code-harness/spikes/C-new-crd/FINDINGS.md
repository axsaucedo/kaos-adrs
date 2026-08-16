# Spike C — what `AgentHarness` + `CodingSession` actually costs

**Question.** What does a new CRD cost, and what does it buy over spike A?

**Gate: passed.** Types compile, `controller-gen` produces valid CRDs, and sample CRs validate against them.

## What was built

`api/v1alpha1/codingsession_types.go` — two CRDs following kaos's own marker and field conventions:

- **`AgentHarness`** (`ah`) — reusable template: `runtime`, `modelAPI`/`model`, `credentialsRef`, `mcpServers`, `runtimeClassName`, `container`, `podSpec`.
- **`CodingSession`** (`cs`) — one run: `harnessRef`, `prompt`, `repo`, `mode`, `budgets`, `ttlSecondsAfterFinished`.

Generated and validated:

```
AgentHarness:  VALID
CodingSession: VALID
```

## Cost

| | Lines |
|---|---|
| Hand-written types | **198** |
| `groupversion_info.go` | 14 |
| Generated deepcopy | 346 |
| Generated CRD YAML (`CodingSession`) | 226 |
| Generated CRD YAML (`AgentHarness`) | 9,041 |
| **Controllers — not written** | **~1,200–1,500 estimated** |

The controller estimate comes from kaos's own reconcilers: `mcpserver_controller.go` is 525 lines, `memorystore_controller.go` 652, `agent_controller.go` 1,372. A `CodingSession` controller does more than MCPServer (Job lifecycle, PVC, git credentials, status propagation from pod to CR, TTL cleanup) and less than Agent (no gateway routing, no memory scope validation), so ~700–900 for the session reconciler plus ~300–500 for the harness reconciler is the honest range.

**So the real cost is roughly 1,400–1,700 lines of net-new operator code**, of which the type definitions — the part this spike actually wrote — are only 198. The types were the cheap part; the spike does not pretend otherwise.

Two incidental findings:

- The `AgentHarness` CRD YAML is **594KB / 9,041 lines**, entirely because it embeds `corev1.PodSpec`. This is not new — the existing Agent CRD has the same property — but it is worth knowing that adding a second PodSpec-embedding CRD roughly doubles the chart's CRD payload.
- `ContainerOverride` here adds `securityContext`, `workingDir`, and `volumeMounts`, the three fields spike A found missing. Adding them costs **3 lines** on the existing Agent CRD and needs no new kind at all.

## What it buys that spike A cannot reach

Ordered by how much it actually matters, after spike A disproved the parallelism argument:

1. **The pod as the session boundary.** Per-session CPU/memory limits, independent failure, and a restart that costs one session rather than all of them. Spike A multiplexes sessions inside one pod, so it can offer none of this.
2. **A status object.** `CodingSessionStatus` carries `phase`, `branch`, `pullRequestURL`, `commitSHA`, `filesChanged`, `startTime`/`endTime`. `kubectl get codingsessions` becomes meaningful:
   ```
   NAME        HARNESS   PHASE       BRANCH                   PR                          AGE
   fix-flaky   claude    Completed   kaos/session-fix-flaky   github.com/.../pull/312     4m
   ```
   Spike A has nowhere to put any of this — `AgentStatus` has no run fields, so session listing must come from an HTTP call to the pod.
3. **Completion and cleanup semantics.** A `Job` has terminal phases and `ttlSecondsAfterFinished`; a `Deployment` never finishes.
4. **Horizontal spread.** Sessions schedule across nodes instead of being capped by one pod's resources.
5. **Per-session `runtimeClassName`.** gVisor or Kata per session rather than per agent.

## What it does not buy

- **Not parallelism.** Spike A demonstrated 4 concurrent addressable sessions with distinct workspaces in a single pod. The claim that `replicas := int32(1)` blocks fan-out was wrong, and it was the main argument for this CRD in the design draft.
- **Not Mode 2.** The mode we decided to ship first works today with zero operator changes.
- **Not a registry.** With one harness and no operator-side branching on harness type, `kaos-harness-runtimes` would have no consumer — repeating the `RequiredEnv` mistake of a field introduced with nothing reading it. `spec.runtime` is left unconstrained here to match `MCPServer.Spec.Runtime`, but the ConfigMap itself should wait for a second harness that needs differentiated treatment.

## Recommendation for design question 2

**Do not build this first.** The evidence across spikes A, C, and S points to a sequence rather than a choice:

1. **Phase 1 — spike A's shape.** Harness as an `Agent` flavour. Zero operator change. Ships Mode 2.
2. **Phase 1.5 — three fields.** Add `securityContext`, `workingDir`, `volumeMounts` to the existing `ContainerOverride`. ~3 lines of types; removes the main ergonomic wart spike A found.
3. **Phase 2 — this CRD.** Build `CodingSession` when per-session isolation or `kubectl get` visibility is actually wanted. Of the two, the **status object is the more likely trigger** — isolation matters only for untrusted or multi-tenant work, but "what is my session doing, and where is the PR" is wanted on day two.

If phase 2 arrives, `AgentHarness` may not be needed alongside `CodingSession`: an `Agent` CR configured as a harness could serve as the template, with `CodingSession.harnessRef` pointing at it. That would halve the new API surface and reuse the gateway, authz, and memory wiring already attached to `Agent`. Worth testing before committing to two kinds.

## Not verified

- **No controller was written.** This is the single largest gap: the ~1,200–1,500 line estimate is extrapolated from kaos's existing reconcilers, not measured. Job lifecycle, PVC provisioning, and status propagation from pod to CR are all unimplemented, and each could surprise.
- Not applied to a cluster. CRDs were validated against their generated OpenAPI schema, not installed; no envtest or KIND run.
- No CEL `XValidation` rules, which the real Agent CRD uses extensively for memory-config invariants. Equivalents here (e.g. `mode: interactive` requiring a TTL, `repo` required unless a workspace is supplied) are unwritten.
- The types live in a standalone module (`spike/c-new-crd`), not in `operator/api/v1alpha1`, so they were never compiled against the real operator's scheme or client.
