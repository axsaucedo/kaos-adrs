# Spike plan — KAOS coding harness

Five spikes across three waves. Each spike answers one question with running code, not prose. A spike that cannot answer its question inside its self-limit reports *that* as the finding and stops.

## Ground rules

- **Byte-sized commits.** Every meaningful step commits. Conventional commits, scoped to the spike: `spike(H): containerize pi headless`.
- **Worktrees for parallel tracks.** Each wave-2 spike runs on its own branch in its own worktree off `kaos-ai-docs`, merged back to `main` for review when its gate passes.
- **Self-limit: ~45 minutes of active work per spike.** Past that, write down where it got to and what blocked it.
- **Findings beat artifacts.** A spike's deliverable is `FINDINGS.md`. Code exists to make the findings honest, not to be reused.
- **Negative results are results.** "This does not work, here is exactly where it breaks" is a passing spike.

## Wave 1 — H: which harness

Everything downstream needs a harness that runs headlessly in a container. This wave picks it.

**Question.** Which of `pi`, Codex CLI, Claude Code, Hermes is cheapest to containerize, drive headlessly, and run in CI — and is that the same one that should be the headline harness?

**Deliverables.**
- A `Dockerfile` per candidate that builds (or a documented reason it cannot).
- A headless invocation script per candidate proving a prompt in, a result out.
- A comparison table: license, image feasibility, credential friction, arbitrary-endpoint support, driver surface, CI viability.

**Gate.** At least one harness builds and runs headlessly with no proprietary credential. If none does, wave 2 becomes design-only and says so.

**Steer trigger.** If `pi` turns out to lack a usable non-interactive mode, or cannot point at an OpenAI-compatible endpoint, Codex CLI becomes the scaffold and waves 2–3 rebuild against it.

## Wave 2 — A vs C vs S, in parallel worktrees

Three answers to "where does a coding session live in the API". Same question, three architectures, built against whichever harness wave 1 picked.

### A — harness as an `Agent` flavour (no new CRD)

**Question.** Can a coding harness be deployed as an unmodified KAOS `Agent`, and where is the ceiling?

The bet: the operator never talks to the process inside an agent pod — it resolves dependencies into env vars and talks HTTP to `:8000`. If a harness image exposes the same surface the pydantic-ai runtime does, the operator cannot tell the difference.

**Deliverables.** A harness image serving the existing contract (`/v1/chat/completions` with KAOS's SSE chunk shape, `/.well-known/agent.json`, A2A JSON-RPC routes). An `Agent` CR that deploys it **with no operator changes**, using `spec.podSpec` for the workspace. A written ceiling: the first thing that cannot be expressed.

**Gate.** Either it deploys and serves a task end to end, or the exact blocking field/behaviour is named.

### C — `AgentHarness` + `CodingSession`

**Question.** What does a new CRD actually cost, and what does it buy over A?

**Deliverables.** Go types, `make generate manifests` output, a controller sketch that reconciles a `CodingSession` to a `Job` with a workspace and a `/state` volume. A line count of net-new operator code. An explicit list of capabilities that A cannot reach.

**Gate.** CRDs generate cleanly and the capability delta over A is stated concretely, not hypothetically.

### S — split loop from execution

**Question.** Can the harness hold the agent loop while a separate sandbox pod holds the workspace and executes — and what does the harness lose?

The suspected blocker: Claude Code, Codex, and `pi` all ship native Bash/Read/Edit tools bound to the local filesystem. Forcing MCP-only execution may mean discarding the tuned toolset that is most of the reason to use a harness.

**Deliverables.** An attempt to disable native filesystem/shell tools and route them to a remote MCP server. A finding on whether each harness permits it, and what breaks when it does.

**Gate.** A clear feasible / infeasible verdict with the mechanism named.

## Wave 3 — D: driver contract

**Question.** ACP as a uniform internal contract, or a per-harness native driver?

Runs after wave 2 because the answer depends on where the driver lives.

**Deliverables.** Two prototype drivers against the wave-1 harness — arm A over ACP, arm B over the harness's native surface. Lines of code each, fidelity lost, and whether ACP's stdio-only constraint forces a shim like kagent's `acp-shim`.

**Gate.** A direct comparison on the same harness, not two descriptions.

## Merge and report

Each spike merges to `main` when its gate passes. `RESULTS.md` consolidates, then the design discussion's questions 2, 3, 4, and 9 get resolved from evidence.
