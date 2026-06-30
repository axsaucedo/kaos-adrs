# M1 — atomic stores — progress

Status: complete.

All six tasks executed against running code. The `memory-service/` package (`kaos_memory`) now provides the two atomic, independently-testable storage primitives the later phases compose into a deployable service. Implemented on a branch stacked off `main`, every task committed individually with a comprehensive functional message, and the full suite is green in both storage modes (32 tests: local Chroma/SQLite plus pgvector/Postgres behind the `pgvector` marker).

## Tasks

1. **Package scaffold** — `memory-service/` with `pyproject.toml` (pinning `mem0ai==2.0.10`, `chromadb`, `psycopg[pool]`, `pgvector`, `tiktoken`, `httpx`), `Makefile` (build/test/lint/format mirroring the rest of the Python CI), and the `kaos_memory` package plus test scaffolding.
2. **Config + scope value objects** — `config.py` (typed `StorageConfig`/`LocalStorage`/`ExternalStorage`/`ModelConfig`/`WorkingTierConfig` with a `.resolved()` accessor) and `scope.py` (`Scope`, `ScopeLevel`, the reserved shared-owner key, and the Mem0 owner mapping). 15 tests.
3. **Long-term adapter** — `longterm.py`, the only importer of `mem0`, exposing `write`/`recall`/`delete`/`delete_scope` with scope owner filters applied inside the vector query. Mem0 telemetry disabled at import. 5 tests (3 local + 2 pgvector).
4. **Working-tier store** — `working.py` + `tokens.py`: a scope-keyed relational buffer with a token budget and rolling summary, eviction-by-summarization (never truncation), over a `_Backend` abstraction that hides SQLite vs Postgres. 8 tests (SQLite + Postgres).
5. **Model client** — `models.py`: an OpenAI-compatible chat-completions binding for working-tier summarization, driven by the same `ModelConfig` as Mem0's extraction/embedding, with an `as_summarizer` adapter for the working store. 3 tests via a mocked transport.
6. **Composition smoke + README + CI** — `test_stores_smoke.py` drives both stores for one scope in local mode; a package `README.md` documents the scope model, storage modes, and how to run the pgvector tests; and the Python CI gained `memory-service-lint` and `memory-service-tests` jobs (the latter with a pgvector service container).

## Validation

- `pytest tests/ -v` — 32 passed (local + pgvector).
- `make lint` — `black --check` clean, `ty` clean.
- pgvector path exercised against `pgvector/pgvector:pg16` via `KAOS_TEST_PGVECTOR_DSN`.

Findings and the deltas to fold into M2 are recorded in [`../learnings/M1-atomic-stores.md`](../learnings/M1-atomic-stores.md).
