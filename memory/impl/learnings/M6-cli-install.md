# M6 — CLI install integration, sample, and worked example — learnings

Deltas and gotchas that emerged while making the memory feature turnkey and verifying it end to end on a live KIND cluster. These supersede the corresponding assumptions in the M6 plan where they differ and feed the later productionisation work.

## Agent memory config lives at `spec.config.memory`, not `spec.memory`

The agent memory block is a field on the `AgentConfig` Go struct, so its CRD path is `spec.config.memory`, not the top-level `spec.memory` a first read of the sample suggested. The API server strict-decodes and rejects a stray top-level `memory:` block, so a sample or manifest with the wrong nesting fails to apply even though every field name is correct. The sample and the CLI dry-run assertion were corrected to the nested path. This is the single most load-bearing shape detail for anyone hand-writing a memory-bound Agent.

## The pgvector external backend needs libpq in the image

An `external`-mode `MemoryStore` failed to start with `ImportError: Neither 'psycopg' nor 'psycopg2' library is available`. The `psycopg[pool]` dependency is the pure-Python psycopg build, which still loads the system `libpq` shared library at runtime to reach Postgres — and the `python:3.12-slim` base image ships no libpq. The fix is a one-line `apt-get install -y libpq5` in `kaos-memory/Dockerfile`. This was deliberately chosen over switching to `psycopg[binary,pool]`: the binary extra pulls `psycopg-binary` into the dependency graph and would require regenerating `uv.lock`, which is blocked in this environment, whereas installing the system library keeps the lock untouched and the runtime correct.

## The dev pgvector Secret must be copied into the agent's namespace

`--pgvector-memory-enabled` writes the `kaos-memory-pgvector` connection Secret into the install namespace (`kaos-system`). An `external`-mode `MemoryStore` resolves its `connectionSecretRef` in **its own** namespace, so when the store lives in an application namespace the Secret has to be copied there first (`kubectl get secret kaos-memory-pgvector -n kaos-system -o yaml | ... | kubectl apply -n <app-ns> -f -`). This cross-namespace copy is the one manual step the worked example's external variant calls out; a future ergonomic improvement would be for the installer or controller to project the DSN into consuming namespaces.

## The pgvector `vector` extension is created lazily, not at store startup

A freshly-`Ready` external store creates only the short-term and medium-term tables (`short_term_memory_window`, `medium_term_memory_summaries`) eagerly. The `CREATE EXTENSION vector` and the mem0 long-term vector table are created **lazily on first long-term extraction**, which requires a real embedder. So with a placeholder embedding key the vector extension never appears and recall reports `degraded:true` for the long-term tier only — the verbatim short-term window still round-trips correctly. This confirms an earlier open question: store readiness does not depend on, and does not trigger, the vector extension.

## Model-independent examples must poll through the full pod-startup window

The worked example port-forwards to the memory service and polls `/healthz`. While the pod is still starting, the forwarded socket accepts the TCP connection but the upstream drops it, which httpx raises as `RemoteProtocolError` — not `ConnectError`. Catching only `ConnectError` aborts the readiness loop prematurely; the loop must catch `httpx.HTTPError` (or equivalently retry on any transport error) to span the entire startup window. This is the kind of timing bug that only surfaces against a real cluster, not in a dry-run.

## The model-independent contract path is what makes the example CI-safe

Driving the example through the memory service `/v1/write` + `/v1/recall` contract with `infer:false` exercises the verbatim short-term round-trip, scope isolation, and recovery without any model call. That is what lets the default example run in a KIND shard with a mock ModelAPI and no embedder, while the real semantic-recall behaviour is demonstrated separately in the manually-verified pgvector variant. Keeping the two paths explicitly separated stops the real-embedder cost from inflating default CI.

## Long Typer flags wrap in Rich `--help` at the default test width

The `--pgvector-memory-enabled` flag is long enough that Rich wraps it across lines in `--help` output at the default `CliRunner` width, breaking substring assertions. Invoking with `env={"COLUMNS": "200"}` widens the render so the flag and its help text land on assertable single lines. Worth remembering for any future flag past ~20 characters.
