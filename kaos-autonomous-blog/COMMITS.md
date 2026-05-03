# Curated Commit Inventory: KAOS v0.4.0 Autonomous/A2A Work

Source range:

```bash
git log --reverse --format='%h %s' v0.3.1..v0.4.0
```

This file groups the release commits by article-relevant surface. It is intentionally curated so the article can use the implementation as evidence without becoming a changelog.

## A2A and Autonomous Runtime

| Commit | Message |
| --- | --- |
| `1e415b9e` | feat(pais): wire TaskStore into AgentServer and create_agent_server factory |
| `490e53d8` | feat(pais): add task execution engine with async submit, execute, and cancel |
| `2d8b6806` | feat(pais): add A2A JSON-RPC POST / endpoint with tasks/send, tasks/get, tasks/cancel |
| `bf406b46` | feat(pais): update agent card with A2A capabilities and supported protocols |
| `aae2a9c1` | test(pais): add A2A integration tests for task lifecycle, concurrency, and memory |
| `4dd14279` | refactor(a2a): extract TaskManager and JSON-RPC into pais/a2a.py module |
| `b01cdce3` | feat(a2a): add A2A RC v1.0 spec-compliant method names with blocking mode |
| `df21b229` | feat(a2a): add OpenTelemetry observability to TaskManager |
| `db79198f` | feat(a2a): update RemoteAgent to use A2A SendMessage for delegation |
| `d1010eba` | fix(a2a): propagate delegation metadata through A2A SendMessage path |
| `a7a26514` | refactor(a2a): redesign TaskManager as ABC with LocalTaskManager and NullTaskManager |
| `deb9f650` | refactor(a2a): make SendMessage synchronous, remove async task execution |
| `df4df6ac` | feat(a2a): extend Task data model with event log, mode, AutonomousBudgets |
| `c7f1a0ec` | feat(autonomous): implement _run_autonomous loop with budget enforcement and completion detection |
| `4056c417` | feat(a2a): extend TaskManager ABC with submit_autonomous and async execution |
| `b2af75ff` | feat(autonomous): add startup-activated autonomous mode via lifespan and env vars |
| `9b40053c` | feat(a2a): add autonomous mode support to A2A SendMessage with budgets and async execution |
| `1a4e6647` | feat(autonomous): support unlimited budgets with 0 sentinel value |
| `7ee50581` | feat(autonomous): add intervalSeconds for pause between loop iterations |
| `f8525c67` | refactor(pais): extract _run_agent helper with actual tool call counting |
| `844ed1e3` | refactor(pais): consolidate autonomous loop into LocalTaskManager |
| `3ffb1e3e` | refactor(python): split autonomous into ContinuousConfig and TaskBudgets with dual execution paths |
| `84fad1f1` | refactor(python): rename ContinuousConfig→AutonomousConfig, Task.mode→autonomous bool, remove autonomous_enabled |
| `71d86656` | refactor: rename is_crd_mode to is_autonomous and remove 'continuous' terminology |
| `0b383f5d` | refactor(python): simplify TaskEvent to state transitions only — remove iteration events |
| `195dbbfb` | fix(python): correct memory event storage order for tool calls |
| `f79b71ca` | fix(python): make autonomous CRD-mode resilient to iteration failures |

## Operator and Kubernetes API

| Commit | Message |
| --- | --- |
| `7c33fd47` | feat(crd): add AutonomousConfig to Agent CRD with operator env var plumbing |
| `c5654335` | feat(autonomous): validate enabled=true requires goal in CRD and Python |
| `87932016` | fix(operator): check all Status().Update() return values in agent controller |
| `68703011` | refactor(operator): split autonomous config into continuous (CRD) and async task budgets |
| `d05b003f` | refactor(operator): restructure CRD — remove autonomous.enabled, group taskConfig, simplify env var plumbing |
| `200b8245` | feat(samples): add autonomous cluster monitoring sample with kubernetes MCP |
| `772cf3ff` | refactor(cli): remove namespace creation from samples, add modelapi skip |

## CLI

| Commit | Message |
| --- | --- |
| `e5410d56` | feat(cli): add autonomous deploy flags to kaos agent deploy |
| `e2e8fe19` | feat(cli): add kaos agent a2a send/get/cancel subcommands |
| `f11ce4c3` | fix(cli): send status messages to stderr in --json mode |
| `0785c097` | refactor(cli): update autonomous CLI flags and iteration messages for continuous vs async modes |
| `d21c1690` | refactor(cli): remove enabled:true from autonomous YAML, nest task fields under taskConfig |
| `f940c29c` | refactor(cli): replace a2a send --mode with --async flag |

## UI and Debugging

| Commit | Message |
| --- | --- |
| `4a6b1a8d` | feat(ui): sync TypeScript types with Go CRD — add autonomous, taskConfig, telemetry interfaces |
| `4dc10c1e` | feat(ui): add A2A proxy client methods for agent card and JSON-RPC |
| `eb6dfbf6` | feat(ui): add A2A debug screen with SendMessage, GetTask, CancelTask, and task history |
| `308e690a` | feat(ui): enhance memory screen with live mode, conversation view, and session filter |
| `34814580` | fix(ui): auto-switch to Get/Cancel tab when clicking A2A task history |
| `e2f622ba` | fix(ui): rename A2A mode dropdown from 'Autonomous' to 'Async Task' |
| `3f21130d` | fix(ui): add autonomous execution section to agent detail overview |
| `be2ad441` | feat(ui): add markdown rendering to memory conversation view |

## Documentation and Examples

| Commit | Message |
| --- | --- |
| `a973fcac` | docs: add A2A TaskStore and JSON-RPC documentation |
| `a67f5c54` | docs(autonomous): document autonomous execution architecture, configuration, and usage |
| `c3c24467` | feat(examples): add autonomous agent example with E2E test and CI shard |
| `4f262752` | docs: update autonomous docs for continuous vs async task architecture |
| `cbd55e7f` | docs: update autonomous docs and instructions for simplified TaskEvent model |
| `4e2e40d8` | docs: rewrite autonomous-agent example with Python cells and production walkthrough |
| `b7aadf42` | docs: rewrite autonomous example with mermaid diagrams, bang syntax, and OpenClaw reference |

## MCP Runtime Context

| PR/Commit | Message |
| --- | --- |
| [#108](https://github.com/axsaucedo/kaos/pull/108) | FastMCP 3.0 upgrade |
| [#109](https://github.com/axsaucedo/kaos/pull/109) | Add `fastmcp-codemode` runtime with CodeMode transform |

## Editorial Takeaway

The commit flow shows a useful engineering pattern:

1. Add a task contract around the agent runtime.
2. Wire protocol endpoints around that contract.
3. Add autonomous looping on top of the same task abstraction.
4. Split always-on autonomy from bounded background tasks.
5. Simplify event boundaries so task state and memory do not duplicate each other.
6. Add UI/CLI surfaces because production autonomy requires inspection and control.

