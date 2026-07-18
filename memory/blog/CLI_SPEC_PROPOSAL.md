# CLI spec proposal: `kaos memory` (admin memory inspection + erasure)

**Status**: proposal for review. Implements the verbs the worked example uses. Ships as its own small PR (off main — it wraps the existing memory-service HTTP API and does not depend on the memory stack).

## Purpose

A `kubectl`-level operator tool to inspect and erase memory in a `MemoryStore`, by explicit scope. It is the admin path: it constructs the scope from flags and calls the memory service directly. It complements, and does not replace, the existing per-agent view (`kaos agent memory`) and the conversational path (`kaos agent invoke`).

## Commands

### `kaos memory recall`
Inspect what a scope holds (long-term facts + optional conversational tiers).

```
kaos memory recall --store <name> --scope <level> [owner flag] \
  [--query <text>] [--short-term] [--top-k <n>] [-n <namespace>] [--json]
```

### `kaos memory forget`
Erase everything a scope holds, across all tiers. Destructive; prompts unless `--yes`.

```
kaos memory forget --store <name> --scope <level> [owner flag] [-n <namespace>] [--yes]
```

## Flags

| Flag | Applies to | Meaning |
| --- | --- | --- |
| `--store, -s <name>` | both | the `MemoryStore` to target. Optional if the namespace has exactly one store (else required). |
| `--scope <level>` | both | one of `session \| agent \| user \| group`. |
| `--session <id>` | scope=session | the session/run id (the owner). |
| `--agent <name>` | scope=agent | the agent name; the CLI expands it to the stored identity `kaos://agent/<ns>/<name>`. |
| `--user <principal>` | scope=user | the stored principal. Verbatim on an OIDC-off cluster; the token `sub` on an OIDC cluster. |
| (none) | scope=group | group is the store itself; no owner flag. |
| `--query <text>` | recall | semantic query for the long-term tier (semantic search). |
| `--all` | recall | list everything at the scope (faithful dump via the service `get_all` path) instead of a semantic query. Mutually exclusive with `--query`. |
| `--short-term` | recall | also return the short-term window + medium-term summary (requires `--session`). |
| `--top-k <n>` | recall | max long-term results (default 10). |
| `--yes, -y` | forget | skip the confirmation prompt. |
| `--json` | recall | raw JSON instead of the pretty view. |
| `-n, --namespace` | both | namespace (falls back to the kube context namespace). |

Validation: the owner flag must match `--scope` (e.g. `--scope user` requires `--user`; supplying `--agent` with `--scope user` is rejected). `--scope group` takes no owner flag.

## Scope → request mapping

The CLI builds the same `Scope` the runtime does and posts it to the service:

| `--scope` + flag | Constructed scope | Service call |
| --- | --- | --- |
| `session --session s1` | `{level: session, session_id: s1}` | `/v1/recall`, `/v1/forget` |
| `agent --agent support-a` | `{level: agent, agent_client_id: kaos://agent/<ns>/support-a}` | same |
| `user --user alice` | `{level: user, principal: alice}` | same |
| `group` | `{level: group}` | same |

## Auth / authorization model

- **No user token.** This is the operator/admin path. The CLI reaches the memory service via `kubectl port-forward` to `svc/memorystore-<store>.<ns>:8080`, exactly as `kaos agent memory` already does for the agent endpoint.
- **Authorization is Kubernetes RBAC.** Being able to port-forward to that service in that namespace *is* the permission gate — the same trust level as `kubectl`. The memory service does no app-level auth; it is protected by NetworkPolicy (only bound agents + operator access) and by not being externally routed.
- Consequently the tool is for operators, and the scope is supplied explicitly (not derived from identity). A future user-facing "show/delete *my* memory" path (persona 2, over the gateway with a user token) is out of scope here and would require the service to grow app-level principal auth.

## Endpoint resolution

- Resolve the `MemoryStore` status endpoint (`status.endpoint`, e.g. `http://memorystore-<name>.<ns>.svc:8080`), or fall back to `svc/memorystore-<name>`.
- Open a `kubectl port-forward` on an ephemeral local port, issue the HTTP call, tear the forward down. Reuse the existing port-forward helper from `kaos-cli/kaos_cli/agent/memory.py` (which already does this for the agent endpoint) so retry/backoff behaviour is consistent.

## recall: query vs list

`/v1/recall` is semantic search over the long-term tier. The worked example needs both modes, so ship both:
- **By meaning** (`--query "EU incidents"`) — passes through recall's search path.
- **List everything** (`--all`) — a faithful dump of the scope. Recall is search, not list, so this needs a small service addition: a `get_all`-backed list path (Mem0 `get_all` with the scope filter + the conversational-tier rows). Worth building as part of this PR, since the example's Part 2 reads as listing and it is the honest surface for GDPR/erasure inspection.

## Related: `kaos agent tools <agent>` (small, adjacent)

The example's Part 3 shows an agent's `search_memory` `level` enum to prove the entitlement boundary. That needs a way to print an agent's exposed tool schemas: `kaos agent tools <agent> -n <ns>` → the tool definitions (name + JSON schema) the agent presents to the model, read from the agent's tool-listing surface. Small, read-only, and reuses the agent port-forward helper. Include it in this PR or split it — flag for review.

## forget safety

- Prints the resolved scope and a summary of what will be erased, then prompts `Erase all memory at scope <...>? [y/N]` unless `--yes`.
- Returns the service's `{forgotten, degraded}` result; non-zero exit on failure.

## Out of scope (recorded, not built)

- User-token self-service (`kaos memory --me` over the gateway) — needs service-side principal auth.
- Write/save from the CLI — memory writes belong to the agent path; an admin write tool is not a use case yet.
- Cross-store operations — one store per invocation.

## Implementation notes

- New command group `kaos memory` in `kaos-cli` (`kaos_cli/memory/…`), sibling to the existing `kaos_cli/agent/memory.py`.
- Reuse the port-forward + retry helper already in `agent/memory.py`; factor it into a shared util if cleaner.
- Contract: the constructed scope JSON must match `kaos_memory.contract.Scope` field names (`level`, `session_id`, `agent_client_id`, `principal`) so it round-trips through the same service validation the runtime uses.
- Tests: dry-run scope construction (flag → scope JSON, incl. the `--agent` → qualified-identity expansion and the scope/owner-flag validation); a mocked-service recall/forget; the forget confirmation prompt.
