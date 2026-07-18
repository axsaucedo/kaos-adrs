# Worked example v2 draft (Blend option)

**Status**: placeholder draft for coherence review. This replaces the current "Worked Example" section of `BLOGPOST_DRAFT_4.md` once approved and once the stack (#280/#282) merges. All command outputs marked `[PLACEHOLDER]` will be replaced verbatim by a capture run. Steps map to the agreed Blend: setup, compaction, continuity via facts, per-session windows, user aggregation, group read, tool enum, two negatives, erasure by user, degradation, plus a fleet teaser.

---

## Worked Example: Watching the Tiers, Scopes, and Failures Work

Let's now take a practical end-to-end example. Instead of a single toy exchange, we will drive the system hard enough to watch each mechanism from this post actually fire: compaction folding turns into a summary, facts being extracted and recalled by meaning, scopes isolating and aggregating, and the failure contract holding when the store disappears.

The setup consists of a `ModelAPI` (a small local model for summarization and embeddings, so extraction genuinely runs), a `local`-mode `MemoryStore`, and three agents bound to it: `assistant-a` and `assistant-b` (both `scope: agent`, `tools: read`, `readScopes: [session, agent, group]`), and `worker-b` (`scope: agent`, no tools) which exists only to prove isolation. Requests carry a user principal (alice) injected at the gateway; with OIDC configured this happens automatically, and in this walkthrough we inject the header directly.

### Part 1: Compaction, Facts, and Continuity

Start a conversation with `assistant-a` and keep going past the short-term token budget. We describe a small incident across a dozen turns (a failing deploy, the rollback, the root cause being a missing config key):

```bash
kaos agent invoke assistant-a -n memory-example -m "We had an incident today, the payments deploy failed twice"
kaos agent invoke assistant-a -n memory-example --session s1 -m "The rollback took 25 minutes because the old image was evicted"
# ... ten more turns describing the incident ...
```

Once the window crosses its token budget, recall the session directly from the service. This single response shows all three tiers doing their jobs:

```bash
curl -s http://localhost:18080/v1/recall \
  -H 'content-type: application/json' \
  -d '{"scope": {"level": "session", "session_id": "s1"}, "query": "what happened with the deploy", "include_short_term": true}'
```

```json
[PLACEHOLDER: recall response showing
 - short_term.recent: only the LAST few turns (the window shrank),
 - medium_term.summary: a rolling narrative of the earlier turns,
 - facts: extracted entries like "the payments deploy failure was caused by a missing config key"]
```

The window holds only the recent turns, the older ones were folded into the rolling summary, and the background extraction distilled durable facts, all without any turn waiting for it.

Now open a completely new session and ask by meaning, with words that never appeared in the conversation:

```bash
kaos agent invoke assistant-a -n memory-example --session s2 -m "What was the root cause of the outage?"
```

```
[PLACEHOLDER: reply referencing the missing config key, recalled from facts]
```

Two things worth verifying here. First, the new session's short-term window contains nothing from the first session (windows are per-session), which we can confirm directly:

```bash
curl -s ... -d '{"scope": {"level": "session", "session_id": "s2"}, "query": "deploy", "include_short_term": true}'
```

```json
[PLACEHOLDER: short_term.recent contains only s2's turns; facts still recalled]
```

Continuity across sessions flows through the summary and the extracted facts, never through raw turn replay. This is the honest version of "the agent remembers": it remembers what was distilled, the way you remember last week's meeting.

### Part 2: Scopes, Attribution, and the Proofs

Every record written above carries its full attribution: the agent identity, alice's principal, the session, and the store's group. That allows the same data to be read at different levels. Alice now talks to a *different* agent:

```bash
kaos agent invoke assistant-b -n memory-example -m "For the postmortem, remind me what I told the other assistant about the rollback"
```

A `user`-level recall aggregates everything alice contributed through any agent:

```bash
curl -s ... -d '{"scope": {"level": "user", "principal": "alice"}, "query": "rollback", "include_short_term": false}'
```

```json
[PLACEHOLDER: facts from both assistant-a and assistant-b conversations, all carrying alice's user id]
```

And a `group`-level recall shows what is shared across every agent on the store:

```bash
curl -s ... -d '{"scope": {"level": "group"}, "query": "deploy incident", "include_short_term": false}'
```

```json
[PLACEHOLDER: group-visible facts]
```

The explicit tools respect the same boundaries. `assistant-a` was given `readScopes: [session, agent, group]`, so its `search_memory` tool exposes a `level` parameter whose enum contains exactly those three values, and nothing else:

```
[PLACEHOLDER: tool schema excerpt showing "level": {"enum": ["session", "agent", "group"]}]
```

`user` is absent from that enum, so the model cannot even *express* a user-level search on this agent, and a crafted call with `level: "user"` is rejected at validation before it reaches the service:

```
[PLACEHOLDER: rejection output / log line]
```

Isolation holds in the other direction too. `worker-b` shares the store, the database, and the tables, but an `agent`-level recall with its identity returns none of the incident:

```bash
curl -s ... -d '{"scope": {"level": "agent", "agent_client_id": "kaos://agent/memory-example/worker-b"}, "query": "deploy", "include_short_term": true}'
```

```json
[PLACEHOLDER: empty facts, only worker-b's own turns if any]
```

Finally, erasure. Because every record carries alice's principal, one `forget` reaches her contributions in every partition, across both assistants and all her sessions:

```bash
curl -s http://localhost:18080/v1/forget \
  -H 'content-type: application/json' \
  -d '{"scope": {"level": "user", "principal": "alice"}}'
```

```json
[PLACEHOLDER: forget response; follow-up recalls at user, agent, and group level showing her records gone, worker-b's data untouched]
```

This is the compliance answer in one operation: "delete everything you know about alice" does not require knowing which agents she talked to.

### Part 3: Unplugging the Memory

The failure contract says a memory outage degrades an agent and never stops it, and this is directly testable: delete the store out from under a running agent.

```bash
kubectl delete memorystore shared-memory -n memory-example
kaos agent invoke assistant-a -n memory-example -m "Are you still there?"
```

The invocation succeeds with no memory behind it, and the operator surfaces the state as a condition instead of an outage:

```bash
kubectl get agent assistant-a -n memory-example \
  -o jsonpath='{.status.conditions[?(@.type=="MemoryDegraded")]}'
```

```json
[PLACEHOLDER: MemoryDegraded=True, reason MemoryStoreNotReady]
```

Re-apply the `MemoryStore`, wait for `Ready`, and the agent picks its memory back up on the next turn, with the condition clearing to `MemoryHealthy`. No restarts, no code, and no incident: the difference between an outage and a status condition.

### Per-User by Default, When Identity Is On

This example ran without user authentication, so `agent` scope meant "this agent" and we reached per-user behaviour through the explicit `user` scope. On a cluster with OIDC enabled, that flips automatically: the operator detects user identity is configured and the `agent` scope becomes "this agent, for this authenticated user" on every operation, keyed by both the agent and the verified principal from the gateway. Two consequences fall out of it. Alice and Bob talking to the same assistant get entirely separate memory with no configuration at all. And the derivation is fail-closed: if user scoping is required but a request carries no verified principal, the operation errors rather than falling back to a shared pool, so there is no principal-less partition to leak into. Nothing in the agent's own config changes; the cluster's identity posture decides it.

### Where This Composes: Fleets That Learn

One configuration we did not run here deserves a mention, because it is where the pieces above compose. An agent can set `defaultReadScope: group`, meaning its automatic baseline recalls the *fleet's* knowledge before every run. Combine that with an always-on autonomous agent from the [autonomous agents post](https://hackernoon.com/) publishing its findings at group level, and you get a fleet where one agent's observations become every agent's context, with the group boundary, the attribution, and the erasure semantics above all still holding. That composition is its own post; the primitives it needs are the ones you just watched work.

---

## Capture run notes (not part of the blog text)

- Requires the stack (#280/#282) + OIDC (#286) images; summarization + embedding via Ollama (qwen-class + nomic-embed-text per the earlier e2e setup). Core example runs OIDC-off with explicit scopes; principal injected via the header mechanism documented in the validation report.
- The `--session` flag shape and the exact recall/forget payload fields must be verified against the CLI/service at capture time (session id addressing changed with per-session windows).
- Placeholders map 1:1 to validation matrix cases: P4/P5 (Part 1), P1/P2/P3/P6/N1/N3 (Part 2), P7 (erasure), Part 3 (degradation, already captured in the first blog run). The "Per-User by Default" beat is prose only (no capture) — the OIDC per-user cases are covered by the comprehensive validation on the auth-enabled cluster, not re-run here.
- Bug-fix note: this draft assumes the fixed behaviour (true per-session windows P4, working cross-session dedup P5, complete user erasure P7) — all now landed on the stack; the capture must show the fixed outputs, not the pre-fix ones.
- Slimming candidates if the section proves too long for the post (per review): the tool-schema excerpt, the second negative, and the group-level recall can each drop to one sentence.
