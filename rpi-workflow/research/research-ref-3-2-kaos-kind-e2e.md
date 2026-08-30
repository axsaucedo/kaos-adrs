# research-ref-3-2 — kaos repo's kind-based e2e validation

Source: `/Users/asaucedo/Programming/agentic/kaos`, primarily `operator/Makefile` and `operator/tests/e2e/`. Light survey, not exhaustive.

## Makefile target structure

`operator/Makefile` exposes a `.PHONY` list including `kind-create kind-delete kind-load-images kind-e2e-install-kaos kind-e2e-run-tests e2e-test e2e-test-seq e2e-clean` plus per-feature variants (`kind-load-aib-images`, `kind-e2e-install-aib`, `e2e-test-aib`, `kind-e2e-aib`, and the equivalent `-authz` set). The `help` target documents each:

```
kind-create           - Create KIND cluster with registry, Gateway, MetalLB
kind-delete           - Delete KIND cluster
kind-load-images      - Build and load images into KIND (matches chart defaults)
kind-e2e-install-kaos - Install KAOS operator with Gateway API enabled
kind-e2e-run-tests    - Run E2E tests (depends on load-images + install-kaos)
e2e-test              - Run E2E tests (parallel, requires operator)
e2e-test-seq          - Run E2E tests sequentially
e2e-clean             - Clean up E2E test resources
```

The chain is composable: `kind-create` → `kind-load-images` → `kind-e2e-install-kaos` → `e2e-test`, or the single umbrella `kind-e2e-run-tests: kind-load-images kind-e2e-install-kaos` followed by a script. Cluster lifecycle (create/delete) is separated from image loading, which is separated from install, which is separated from running tests — each stage independently re-runnable so a developer iterating on tests does not pay cluster-recreation cost every loop.

## Parallelisation

```makefile
e2e-test:
	@cd tests && \
	CPUS="$$(nproc --all 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"; \
	JOBS="$$(( CPUS > 4 ? 4 : CPUS ))"; \
	uv run pytest e2e/ -v -n "$$JOBS" --dist loadscope
```

Uses `pytest-xdist` with `-n` sized to the host's CPU count, explicitly capped at 4 — the comment reads "Cap at 4 workers to avoid 'out of pty devices' errors on high-CPU machines," i.e. parallelism is bounded by a concrete observed failure mode, not just "as many workers as possible." `--dist loadscope` groups tests by scope (module/class) onto the same worker, which matters against a *shared* live cluster: tests that share expensive fixtures (a namespace, a deployed ModelAPI) run on one worker rather than racing each other across workers. A parallel `e2e-test-seq` target exists for debugging (`-s --log-cli-level=DEBUG`), since parallel output interleaves and is hard to read when something fails.

## Test layout

`operator/tests/e2e/` contains one file per feature area, each several hundred lines: `test_agentic_loop_e2e.py`, `test_authz_policy_projection_e2e.py`, `test_aib_credential_e2e.py`, `test_modelapi_e2e.py`, `test_memory_store_e2e.py`, `test_multi_agent_e2e.py`, `test_a2a_e2e.py`, `test_mcp_tools_e2e.py`, `test_examples_e2e.py`, `test_base_func_e2e.py`, plus a shared `conftest.py`. File-per-feature (not file-per-endpoint or file-per-function) keeps related fixtures and setup local while still letting `--dist loadscope` parallelise across files.

Test names are workflow-shaped, not input/output-equality shaped, e.g. in `test_agentic_loop_e2e.py`: `test_agentic_loop_config_applied`, `test_delegation_with_memory_verification`, `test_agent_processes_with_memory_events`, `test_coordinator_has_delegation_capability`, `test_wait_for_dependencies_false`. Each asserts on the outcome of a multi-step interaction (deploy a CR, wait for it to become ready, exercise it through the gateway, assert an observable side effect such as a memory event or a delegation happening) rather than "does function X return Y for input Z."

`conftest.py` builds real Kubernetes/Gateway plumbing rather than mocks: `GATEWAY_URL` (defaults to `http://localhost:80`, overridable for KIND), `gateway_url(namespace, resource_type, resource_name)` builds a real routed URL, `create_custom_resource` shells out to `kubectl apply`, `wait_for_deployment` polls with a timeout, `async_wait_for_healthy` retries a `/health` GET with backoff and a post-success stabilization delay "to handle gateway flapping." This is real end-to-end infrastructure: an actual cluster, actual CRs, actual HTTP through the actual gateway — the "e2e as king" principle realised as literally standing up the system and driving it, not stubbing layers.

## What makes it fast/agile

- Cluster lifecycle, image load, install, and test run are separate Makefile targets so nothing is rebuilt/redeployed that does not need to be.
- `e2e-test` assumes a cluster is already up — cost of cluster creation is paid once, not per test run, during iteration.
- Parallel workers are capped by an empirically discovered ceiling (pty exhaustion), not left unbounded — parallelism used deliberately, not maximally.
- A sequential fallback target exists specifically for debugging output legibility, acknowledging parallel test output is a real cost when something fails and needs to be read.
- `--dist loadscope` avoids cross-worker races against shared cluster-level state (namespaces, installed CRs) that a naive `-n auto` distribution would risk.

## Relevance to the RPI plan-stage encoding

The kind e2e pattern is the model for "parallelise past a time threshold, keep execution fast, real e2e over mocks" when the artifact under test is a live, stateful system (a cluster, a deployed service) rather than a single local process like the Streamlit case. Two patterns for two artifact shapes: Streamlit's is "boot one local process, drive a browser against it, tiered escalation"; kind's is "stand up a real cluster once, run many workflow-level tests against it in bounded parallel, tear down." The RPI plan stage should recognise both shapes and let the ADR/plan pick the applicable one per PR rather than force one universal harness.
