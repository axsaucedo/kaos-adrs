# Spike D — ACP as a uniform contract vs a per-harness native driver

**Question.** Should the driver speak ACP to every harness, or each harness's own protocol?

**Gate: passed.** Both arms were driven against the same harness (`pi` 0.84.2) and the same scripted turn — one `bash` tool call, then a final message — so the comparison is like-for-like rather than two descriptions.

## Arm B — native (`pi --mode rpc`)

25 events, newline-delimited JSON, LF-only:

```
response  agent_start  turn_start
message_start message_end                      (user)
message_start message_update ×3 message_end    (assistant → toolCall)
tool_execution_start  tool_execution_update ×2  tool_execution_end
message_start message_end                      (toolResult)
turn_end
turn_start  message_start message_update ×3 message_end  turn_end
agent_end
```

Each `message_update` carries a usage block:

```json
{"type":"message_update","usage":{"input":0,"output":0,"cacheRead":0,
                                  "cacheWrite":0,"totalTokens":0,"cost":...}}
```

`tool_execution_*` carries `toolCallId`, `toolName`, raw `args`, streaming `partialResult`, and the full result payload.

## Arm A — ACP (`pi-acp` 0.0.33)

10 `session/update` notifications for the identical turn, after an `initialize` → `session/new` → `session/prompt` handshake:

```
session_info_update
agent_message_chunk           "pi v0.84.2\n---\n"
available_commands_update
tool_call                     toolCallId, title "echo hi", kind "execute", status pending
tool_call_update ×4           pending → in_progress → in_progress → completed
agent_message_chunk           "ACP_DONE"
session_info_update
→ result {"stopReason":"end_turn"}
```

## The comparison

| | Native RPC | ACP |
|---|---|---|
| Events for one tool-call turn | 25 | 10 |
| Handshake | none — write a prompt line | `initialize` → `session/new` → `session/prompt` |
| Tool lifecycle | `start` / `update` / `end` | `tool_call` + `tool_call_update`, explicit `status` enum |
| Tool call classified by kind | no — raw `toolName` | **yes** — `kind: "execute"`, normalized cross-harness |
| Raw tool args and results | **yes** | title + `_meta` only |
| **Token usage** | **yes** | **absent** |
| **Cost** | **yes** | **absent** |
| Terminal / vendor detail | native fields | `_meta` vendor extension |
| Stop reason | inferred from `agent_end` | **explicit `stopReason`** |
| Cross-harness portability | none — remap per harness | **the entire point** |
| Deployment | one binary | **two binaries** — the adapter shells out to `pi`, and requires it on `PATH` (it ignores `PI_BIN`) |

## What decides it for KAOS

**ACP loses token usage and cost, and that is the one thing KAOS most needs.**

Design question 8 resolved with cost attribution as the fast-follow, precisely because KAOS cannot measure fan-out cost today — `pais/serverutils.py:371` hardcodes `{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}`, and Mode 2 fan-out is structurally expensive (research §11: caches isolated per workspace, ~15× tokens for multi-agent). The native stream hands over `input`, `output`, `cacheRead`, `cacheWrite`, `totalTokens`, and `cost` per assistant message. ACP drops all of it.

Against that, ACP's `kind: "execute"` classification and explicit `status` enum are genuinely better than raw tool names for driving KAOS's existing progress-event contract — `{"type":"progress","action":"tool_call","target":"..."}` maps onto ACP almost 1:1, and onto native events only after a per-harness mapping table.

The two are not mutually exclusive, and that is the finding: **ACP's `_meta` is an open vendor-extension channel** — `pi-acp` already uses it for `queueDepth`, `running`, and terminal state. Usage could ride there. But then it is non-standard per harness, which is exactly the portability ACP was chosen for.

Secondary but real: ACP costs a **second binary in the image** and a `PATH` dependency. For a KAOS-shipped harness image that is a packaging detail; for a BYO Claude Code image it means the user must also install `@zed-industries/claude-agent-acp`, which is a materially worse instruction to give.

## Recommendation for design question 4

**Arm B — per-harness native driver — with ACP kept as a fallback for harnesses that only speak it.**

Reasoning:

1. Cost and token accounting are load-bearing for Mode 2 and only the native surface has them.
2. KAOS already has an external contract (SSE progress events + A2A) that clients consume, so the driver's job is to map *into* that, not to expose ACP. A uniform intermediate protocol buys nothing the external contract does not already provide — it just adds a translation step that loses data.
3. Research §16 recorded that adapters narrow the surface; this spike measured it — 25 events to 10, with the numeric fields the gone ones.
4. ACP remains the right choice for a harness whose native surface KAOS does not want to implement. Hermes speaks it natively, and spike H otherwise recommended dropping Hermes — ACP is what would keep it cheap to support later.

Concretely: `driver: pi-rpc | codex-app-server | claude-stream-json | acp` as a per-runtime setting, with `acp` as the generic fallback.

## Not verified

- **Only `pi` was tested.** Claude Code and Codex have their own native surfaces (`--output-format stream-json`, `codex app-server`) and their own Zed adapters; whether the same usage-vs-portability tradeoff holds for them is inferred, not measured. Claude Code's native stream is known to carry usage, so the direction is likely the same, but the ACP adapters differ per harness and `claude-agent-acp` is built on the Agent SDK, so it may preserve more than `pi-acp` does.
- **No driver was actually written for either arm.** Both were probed with ~25-line throwaway clients, so the "lines of code per harness" figure the spike plan asked for is unmeasured. The event-shape comparison is the substantive result; the LOC question remains open.
- Steering (`steer` vs `follow_up`) and approvals were not exercised on either arm. `pi` has no permission concept at all (research §16), so approval fidelity — the thing most likely to differ — could not be tested with this harness. That needs Codex or Claude Code.
