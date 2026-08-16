# Spike results — KAOS coding harness

Five spikes, all gates passed. Three of the four open design questions now have evidence-backed answers, and **two of the design draft's load-bearing assumptions turned out to be wrong.**

| Spike | Question | Verdict |
|---|---|---|
| **H** | Which harness first? | `pi` to build against, Claude Code as headline. Drop Hermes. |
| **A** | Can a harness be an `Agent` flavour? | **Yes, with zero operator changes.** 9/9 contract tests pass. |
| **C** | What does a new CRD cost? | ~1,400–1,700 LOC with controllers. Buys isolation and a status object — not parallelism. |
| **S** | Can the loop be split from execution? | **Yes, 4/4.** The suspected blocker was not real. |
| **D** | ACP or native driver? | Native. ACP drops token usage and cost. |

## The two assumptions that were wrong

**1. "`replicas: 1` blocks parallel fan-out, so Mode 2 needs a new CRD."**

The draft argued that because `replicas := int32(1)` is a literal with no spec field, and Deployment replicas are fungible, "session 3" is unroutable — and since fan-out is the point of Mode 2, Option A is dead.

This conflates *pod* with *session*. Spike A ran **4 concurrent, separately-addressable sessions with distinct workspaces in one pod in 1.1s**, keyed on `X-Session-ID`. Routing to a session is a header, not a Service endpoint. What `replicas: 1` actually costs is isolation and horizontal spread, not parallelism.

**2. "Harnesses ship native filesystem tools that cannot be removed, so the split architecture is impractical."**

Measured on the wire, tools are removable through supported flags. `pi --no-builtin-tools` empties `bash,edit,read,write` while keeping extension tools — a flag that exists precisely for delegated execution. Claude Code's `--disallowedTools` strips all ten filesystem, shell, and network tools. Spike S then had Claude Code write a real file into a **separate** sandbox process over MCP, with path traversal refused.

One trap worth recording: `--allowedTools` does *not* do this. With `--allowedTools Read`, all 22 tools were still advertised — it governs auto-approval, not availability. Only `--disallowedTools` changes what the model sees.

## The constraint nobody predicted

**Three harnesses, three mutually incompatible model wire formats:**

| Harness | Wire format |
|---|---|
| `pi` | `/v1/chat/completions` |
| Codex CLI | `/v1/responses` — Chat Completions **removed**, verified by explicit rejection |
| Claude Code | `/v1/messages` — an OpenAI-shaped endpoint 404s and surfaces as "issue with the selected model" |

KAOS's `ModelAPI` serves only chat completions (`_resolve_model` builds `OpenAIChatModel`). **Exactly one of the three works with it as it stands.** LiteLLM can serve all three, but that is a `ModelAPI` change and belongs in the plan rather than being discovered during implementation.

A useful corollary: all three harnesses completed real turns against `http://127.0.0.1` with `Authorization: Bearer not-needed`. **Any of them can run in KAOS's e2e suite with a mock and no credential** — which voids the prior argument that `pi` was uniquely CI-viable.

## Recommended sequence

The three architecture spikes point at a sequence rather than a choice:

1. **Phase 1 — harness as an `Agent` flavour.** Zero operator change. Ships Mode 2, which is the mode already decided for first delivery. Proven by spike A's 9/9 conformance suite and schema-validated CR.
2. **Phase 1.5 — three fields.** Add `securityContext`, `workingDir`, `volumeMounts` to the existing `ContainerOverride`. ~3 lines of types; removes the one real ergonomic wart, since a coding workload otherwise needs the full `spec.podSpec` escape hatch for all three.
3. **Phase 1.5 — `ModelAPI` wire formats.** Add `/v1/messages` passthrough (Claude Code) and `/v1/responses` (Codex). Without this, only `pi` can use `ModelAPI`.
4. **Phase 2 — `CodingSession`,** when per-session isolation or `kubectl get` visibility is actually wanted. The **status object is the likelier trigger** than isolation: "what is my session doing and where is the PR" is a day-two want, whereas isolation matters only for untrusted or multi-tenant work.
5. **Phase 3 — split execution (Option S),** as an isolation upgrade for untrusted code, not as the starting point. It composes cleanly onto existing primitives (`Agent` = loop, `MCPServer` = sandbox) but doubles pods per session and adds a hop per tool call.

## Deferred deliberately

- **No harness runtime registry yet.** With one harness and no operator-side branching on harness type, `kaos-harness-runtimes` would have no consumer — repeating the `RequiredEnv` mistake of a field introduced with nothing reading it. Wait for a second harness that needs differentiated treatment.
- **No `kaos code` command group.** If a harness is an `Agent`, then `kaos agent invoke` and `kaos agent a2a send` already are the interface. Revisit if phase 2 lands.

## What was not verified

Stated plainly, because several of these could change conclusions:

- **No cluster anywhere.** The Docker daemon was down, so nothing was built as an image or applied to KIND. CRs were validated against committed CRD schemas, which proves expressibility, not reconciliation.
- **No controller was written for spike C.** The ~1,400–1,700 LOC figure is extrapolated from kaos's existing reconcilers, not measured.
- **Spike S used a scripted model throughout.** It proves the split *mechanism*, not that a real model performs well when its tools are renamed `mcp__sandbox__remote_write` while its system prompt references `Write`. This is the single most important follow-up.
- **Spike D tested only `pi`.** Whether Claude Code and Codex show the same usage-vs-portability tradeoff through their own adapters is inferred.
- **Hermes was never run end to end** — provider registration requires an interactive step, which is itself part of why it is recommended for removal.
- Per-session `git clone` cost, tool-call latency across the split, and Copilot CLI generally: untested.
