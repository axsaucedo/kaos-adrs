# P6 — User authentication (Keycloak) and gateway user-auth — implementation plan

**Branch (KAOS)**: `feat/gateway-user-authentication`, stacked off `feat/sync-service-reconciliation` (P5 tip, PR #235); PR targets `feat/sync-service-reconciliation`.
**Tracking issue**: axsaucedo/kaos#231

> **Stacking-base update (read first).** The earlier draft stacked P6 off P3 (`feat/aib-install-and-sync`) because P5 had not been built. **P5 is now complete and CI-green (PR #235, `feat/sync-service-reconciliation`).** Per `proposed-split.md` P5 and P6 are *siblings* off P3, but the work so far is one **linear stack** (P1→P2→P3→P5). Verified: **P5 only touches `sync-service/**`**, while P6 touches `operator/`, `kaos-cli/`, `operator/chart/` — **zero file overlap**. Therefore stack P6 directly off P5's tip to keep the stack linear and conflict-free; PR base = `feat/sync-service-reconciliation`. (The old note's "only overlap is `install.py`" is moot — P5 never touched `install.py`.)

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, **no skipping**. Per task: make the change → validate the relevant tests pass → commit (comprehensive, functional message describing **what** changed and the context; **no** phase/task/ADR references in commit messages, branch names, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on **KAOS** commits.
- Push to the PR and validate CI is green. Run Go/Python tests locally; a KIND cluster (`kind-kaos-e2e`) is available — run 1–3 checks locally before relying on CI; prefer the full suite in CI. Be efficient with testing. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do **not** use `/tmp`. Request a HOST token only when an interactive login step is genuinely unavoidable.
- Keep the git **commit author** as the repo default (`alejandro.saucedo@zalando.de`); push under the `axsaucedo` gh account (the EMU account `alejandro-saucedo_zse` cannot push/PR-comment on the personal repo) and **restore the EMU account afterwards**. Do **not** change the author email when switching gh accounts.
- Stacked PRs into non-main bases don't auto-trigger CI — dispatch via `gh api repos/axsaucedo/kaos/actions/workflows/<id>/dispatches -f ref=feat/gateway-user-authentication` (Go Tests `222389142`, Python Tests `222389143`, E2E Tests `222359246`).
- End: gitignored `REPORT.md` (all prior phases + this work), posted as a PR comment (**not** committed). Copy this plan to `kaos-ai-docs/security-and-identity/plan/P6-gateway-user-authentication.md` and write `impl/progress/P6-*.md` + `impl/learnings/P6-*.md` (kaos-ai-docs commits follow that repo's **no-trailer** convention).

## Problem statement

Add the **human-identity half** of the two-identity model and validate **combined authentication at the gateway**. Today the gateway enforces only `ext_authz` (the agent actor → resource decision) and validates **no JWTs cryptographically**. P6 introduces a user identity provider (Keycloak by default; OIDC, swappable) and makes the operator generate Envoy `jwt_authn` providers on protected routes so that, *before* `ext_authz` runs:

- the **agent actor token** (`x-agent-authorization: Bearer …`, AIB issuer) is cryptographically verified, and
- the **user subject token** (`Authorization: Bearer …`, Keycloak issuer) is verified **when present**.

The **agent provider is required** (the actor is always present on a protected call); the **user provider is optional** because autonomous runs are actor-only (no user subject — confirmed in P0 H4 and ADR-KAOS-009). The CLI `--auth-enabled` path gains a Keycloak install + realm bootstrap and wires `security.userAuth` into the operator. Token exchange (`ext_proc`) and user-delegated third-party grants are **P7**; `spec.security.id` CRD override is **P8**; fine-grained user RBAC is later authorization-policy work (ADR-KAOS-005).

## Current-state grounding (re-verified against merged P2/P3/P5 code, 2026-06-22)

- **Operator security config** — `operator/pkg/security/config.go`: holds only agent-auth fields — `ExtAuthzURL`, `Issuer` (agentAuth issuer), `CredentialSecretPrefix`. Env vars: `SECURITY_AGENT_AUTH_EXT_AUTHZ_URL` / `_ISSUER` / `_CREDENTIAL_SECRET_PREFIX`. Methods (verified): `GetConfig()`, `IsOperational()` (keys on `ExtAuthzURL != ""`), `CredentialMountingEnabled()`, `CredentialSecretName()`, `TokenEndpoint()` (`issuer + /oauth2/token`), `ExtAuthzBackendRef()`. **No `userAuth` / user issuer / audience / jwksUri / `JWTEnabled` anything** (re-verified). The recent `AGENT_AUTH_*` pod-credential rename did **not** touch this admin/operator surface — it correctly stays `SECURITY_AGENT_AUTH_*`.
- **SecurityPolicy generation** — `operator/pkg/security/securitypolicy.go`: `constructSecurityPolicy(params, cfg)` (line 51) builds an unstructured Envoy `SecurityPolicy` with **only** `spec.extAuth` (`failOpen: false`, `headersToExtAuth: [authorization, x-agent-authorization]`, grpc backendRef → ext_authz Service). **No `spec.jwt` block** (`grep -ic jwt` = 0). `ReconcileSecurityPolicy(...)` (line 100) create-or-updates it, a **no-op unless `IsOperational()`**; called from all three controllers inside the `IsOperational()` guard. Tests: `securitypolicy_test.go`, `config_test.go` exist.
- **CLI auth install** — `kaos-cli/kaos_cli/install.py`: under `auth_enabled`, resolves broker endpoints, optionally `_install_aib`, `_deploy_sync_service`, wires the operator via `_build_auth_operator_args(...)` → `--set security.agentAuth.*`. Defaults `_default_ext_authz_url`/`_default_auth_issuer`/`_default_auth_admin_url`. **No Keycloak install, no `userAuth` wiring.** EG pinned to `ENVOY_GATEWAY_VERSION = "v1.4.6"` (install.py:19). Flags in `kaos_cli/system/__init__.py`: `--auth-enabled`, `--auth-namespace`, `--ext-authz-url`, `--auth-issuer`, `--aib-chart-path`, `--aib-values`, `--sync-chart-path`, `--sync-image-*`. **No `--keycloak-*` / `--user-auth-*`.**
- **SDK/runtime (P1, done)**: the `pais` runtime already **forwards the inbound user `Authorization`** header and attaches the agent actor `x-agent-authorization` on outbound hops (#232). Data-plane propagation for two-identity validation already exists; **P6 is gateway + Keycloak + operator config + CLI — not runtime code.**
- **Operator chart** — `operator/chart/values.yaml` + `templates/operator-configmap.yaml`: render the `security.agentAuth.*` block into `SECURITY_AGENT_AUTH_*` env. No `userAuth` block.
- **Confirmed absent today** (grep, ignoring third-party venv): no `keycloak`, no `userAuth`, no `jwt_authn`/`spec.jwt` anywhere in `operator/` or `kaos-cli/`.

**Target (ADR-KAOS-009 §"Two identities" + ADR-KAOS-003)**: `security.userAuth` (issuer, audience, optional jwksUri) and `security.agentAuth.issuer` become **two Envoy `jwt_authn` providers** on the `SecurityPolicy`. `jwt_authn` validates signature/issuer/audience/expiry against JWKS and exposes verified claims; **then** `ext_authz` makes the allow/deny decision on already-trusted identity (the split is intentional — `ext_authz`/AIB is a pure decision point, not a JWKS validator). The actor is the calling agent's own AIB identity (**never** `subject_token.azp`). Autonomous calls have **no** subject (actor-only), so the user provider must tolerate a missing user token.

## Learnings carried in (P0, P3, P5)

- **In-cluster pods only for gateway-adjacent components** (P0): a containerised gateway/Envoy cannot reliably reach a host-process on Docker-Desktop/macOS. Keycloak, AIB and the access-check all run as **in-cluster pods**; never wire the gateway to a host-bound process. All P6 validation is in-cluster.
- **Agents are AIB LocalClients** (P0 H2): KAOS agents are registered **without** `client_id`/`client_uris` so AIB mints the ES256 actor token itself (validatable against AIB's JWKS). This is what makes the **agent** `jwt_authn` provider work against `agentAuth.issuer`'s JWKS. P6 adds the *user* provider alongside; it does not change this.
- **Two independent identity planes** (P0): user/human → Keycloak (subject token); agent/actor → AIB (actor token). Adding Keycloak does **not** make agents ProxyClients. The two providers are independent.
- **The broker is unpublished → full auth e2e is local-KIND only** (P3): KAOS GitHub Actions runs operator unit/envtest, CLI dry-run tests, and the **security-off** e2e suite (which must stay green). The combined-authn path (Keycloak + AIB + gateway) is validated on **local KIND** and documented in `REPORT.md`. Keycloak is an upstream public image (pullable in CI), but the *combined* path still needs the unpublished broker, so it stays local.
- **Default-off contract must hold** (P3): the `jwt` block renders **only** when issuers are configured, so installs without `--auth-enabled` are byte-for-byte unchanged and the security-off operator/e2e suites pass unmodified. Hard acceptance criterion.
- **Provider-agnostic pod creds vs. admin surface** (recent rename): pod-mounted agent credentials use the `AGENT_AUTH_*` prefix (provider-agnostic); the operator/admin config surface stays `SECURITY_*_AUTH_*`. P6's new operator config is admin surface → **`SECURITY_USER_AUTH_*`** (consistent with `SECURITY_AGENT_AUTH_*`).
- **Telemetry standard is OTel/OTLP push** (P5): KAOS standardised metrics on OpenTelemetry (no Prometheus scrape). P6 adds no new metrics, but any incidental observability must follow the OTel convention, not Prometheus.
- **Grant-ownership is a followup, not P6** (recent design discussion): whether the sync service should own/prune broker grants vs. only sync admin-created grants is an ADR followup (consent/intent, P10–P12). P6 does not touch grant ownership; it only adds gateway user-identity validation.

## Design plan (how it fits)

### A. Operator — two `jwt_authn` providers on the SecurityPolicy

1. **Config (`config.go`)** — add a `UserAuth` group:
   - Fields: `UserIssuer` (`SECURITY_USER_AUTH_ISSUER`), `UserAudience` (`SECURITY_USER_AUTH_AUDIENCE`), `UserJWKSURI` (`SECURITY_USER_AUTH_JWKS_URI`, optional — derived from the issuer when empty).
   - Helpers: `JWTEnabled()` → true when the **agent** issuer (`cfg.Issuer`, already exists) and/or **user** issuer is set; a JWKS-resolution helper returning the explicit URI else a derived one. **Derivation rule**: Keycloak/OIDC realm issuer `…/realms/<r>` → JWKS `<issuer>/protocol/openid-connect/certs`; AIB issuer → AIB's OIDC JWKS path. The operator cannot fetch `.well-known/openid-configuration` at template time, so encode the known path per issuer kind and **always allow an explicit override** (`jwksUri`).
   - **Do not** change `IsOperational()` (stays keyed on `ExtAuthzURL`). `JWTEnabled()` is a separate gate purely for emitting the `jwt` block.

2. **SecurityPolicy (`securitypolicy.go`)** — extend `constructSecurityPolicy` to also emit `spec.jwt.providers` **when `JWTEnabled()`**, alongside the unchanged `extAuth`:
   - **agent provider** (`name: agent`) — `issuer: <agentAuth.issuer>`, `remoteJWKS.uri: <agent jwks>`, `extractFrom.headers: [{ name: x-agent-authorization, valuePrefix: "Bearer " }]`, `claimToHeaders` mapping the agent subject/agent_id claim to a trusted header for ext_authz/audit. **Required** (actor always present).
   - **user provider** (`name: user`) — `issuer: <userAuth.issuer>`, `audiences: [<userAuth.audience>]`, `remoteJWKS.uri: <user jwks>`, default `extractFrom` (`Authorization: Bearer`), `claimToHeaders` mapping `sub`/`preferred_username`. **Optional** — autonomous (actor-only) requests carry no user token and must not be rejected.
   - Emit the user provider only when `UserIssuer` is set (agent-only is a valid config, e.g. autonomous-only installs).
   - Keep `extAuth` exactly as-is; in Envoy Gateway, `jwt_authn` runs **before** `ext_authz` in the same SecurityPolicy.

3. **The optionality contract is the #1 design risk — verify on-cluster (EG v1.4.6), do not assume.** EG's `SecurityPolicy.spec.jwt` semantics for "a token may be absent for one provider" are version-specific. The implementer must confirm, on the running EG version (`kubectl get deploy -n envoy-gateway-system envoy-gateway -o jsonpath='{…image}'` — expected v1.4.6), that:
   - (a) valid agent token + **no** user token → **passes** `jwt_authn` (autonomous path),
   - (b) valid agent token + **invalid** user token → **rejected**,
   - (c) **no** agent token → **rejected**.
   Experiment with the field shape under `./tmp/` first (apply a hand-written SecurityPolicy + curl the gateway), then encode exactly the shape that yields (a)+(b)+(c). **Record the exact field shape and the EG version** in `impl/learnings/P6-*.md`.

### B. CLI — Keycloak install + realm bootstrap + userAuth wiring

1. `_install_keycloak(namespace, release, chart_path|published, values, wait)` — mirror `_install_aib`: install Keycloak in **dev/memory mode** (single replica, `start-dev` equivalent, **no external DB**). Prefer a published chart (Bitnami or `codecentric/keycloak`) consumed by the CLI; allow a `--keycloak-chart-path` override for offline/dev, exactly like the AIB path. Keycloak's public image is pullable, so this works in local KIND without building.
2. `_bootstrap_keycloak_realm(...)` — create/import a `kaos` realm with an OIDC client (audience `kaos`, a confidential or direct-access-grant client) and a **non-interactive test user**, **programmatically** via `--import-realm` (a realm-JSON ConfigMap mounted into Keycloak) and/or the Keycloak Admin REST API. This lets the e2e mint a user token **without** an interactive browser login.
3. Defaults: `_default_user_auth_issuer(keycloak_namespace, release)` = `http://<keycloak-svc>.<ns>.svc.cluster.local:8080/realms/kaos`; audience default `kaos`.
4. Extend `_build_auth_operator_args(...)` to also append `--set security.userAuth.issuer=…`, `security.userAuth.audience=…`, and (when provided) `security.userAuth.jwksUri=…` when user-auth is enabled.
5. New flags in `kaos_cli/system/__init__.py`, threaded into `install_command`: `--user-auth/--no-user-auth` (default **on** under `--auth-enabled`), `--keycloak-namespace`, `--keycloak-chart-path`, `--user-auth-issuer`, `--user-auth-audience`. Keep `--auth-enabled` the single convenience switch that now **also** installs Keycloak and wires `userAuth`.

### C. Operator chart

- `values.yaml`: add a `security.userAuth` block (`issuer`, `audience`, `jwksUri`), all empty by default.
- `templates/operator-configmap.yaml`: render `SECURITY_USER_AUTH_ISSUER` / `_AUDIENCE` / `_JWKS_URI` from `security.userAuth`, mirroring the existing `agentAuth` block, **only when set** (default install adds nothing).

### D. Programmatic user-token acquisition (tests/e2e)

- A small reusable, **non-interactive** token helper under `./tmp/security/` that fetches a Keycloak user access token via the **password** (Direct Access Grant) or **client-credentials** grant against the bootstrapped realm/client/user — **no browser**. Decode-and-assert: `iss` matches `userAuth.issuer`, `aud` includes the configured audience. Document the single unavoidable interactive case (real human SSO) as out-of-scope for automated validation.

### E. Manual end-to-end validation against a live cluster (explicit, required)

Beyond unit/dry-run tests, P6 is **not done** until a real, manually-driven end-to-end run proves the combined-authn path on a live cluster. This is a first-class deliverable (T6), executed and captured step-by-step — not a passing assertion in a test file. The procedure:

1. **Run it through the installer.** Use the real CLI path (no hand-applied manifests for the install itself):
   - `kaos system install --gateway-enabled --metallb-enabled --auth-enabled <flags>` against the local KIND cluster (`kind-kaos-e2e`), exercising the *new* P6 code path (Keycloak install + realm bootstrap + `userAuth` operator wiring). Capture the full installer output under `./tmp/`.
2. **Have the cluster that is set up.** Confirm the cluster reaches a healthy steady state with all components actually running:
   - `kubectl get pods -A` shows Keycloak, AIB, sync-service, the operator, Envoy Gateway, and the sample workloads **Running/Ready**.
   - `kubectl get securitypolicy -A -o yaml` shows the generated `spec.jwt.providers` (agent + user) **and** the unchanged `extAuth` on protected routes.
   - `kubectl get deploy -n envoy-gateway-system envoy-gateway -o jsonpath='{…image}'` confirms the EG version (v1.4.6) the jwt shape is locked against.
   - Port-forward the gateway on macOS (`kubectl port-forward -n envoy-gateway-system svc/envoy-gateway 8888:80`; `export GATEWAY_URL=http://localhost:8888`) since MetalLB IPs aren't host-reachable.
3. **Run real commands against it with components that validate everything works.** Deploy a sample `Agent → MCPServer` with a granted edge, then drive **real requests through the gateway** (curl with crafted/real tokens from the T5 helper; suppress noise to `./tmp/null`) and assert observed status codes + component behaviour, not mocks:
   - (a) valid user token **and** valid actor → **200 allowed**;
   - (b) valid actor, **no** user token (autonomous/actor-only) → **200 allowed** (user provider optional);
   - (c) **invalid** user token → **401 rejected by `jwt_authn`**;
   - (d) missing/invalid actor → **401/403 rejected**;
   - (e) granted vs **ungranted** edge → allow vs **deny via `ext_authz`** *after* `jwt_authn` passes.
   - Cross-check the decision path in logs: Envoy access logs (jwt_authn verdict), the AIB ext_authz Check decision, and the sync-service/credential Secret for the agent. Capture each command + its output under `./tmp/`.
   - Optionally also drive the path via `kaos` CLI verbs (e.g. agent invoke / a2a) where they traverse the gateway, to validate the user-facing surface, not just raw curl.
4. **Confirm the default-off contract on the same cluster.** A second install **without** `--auth-enabled` (or with `--no-user-auth`) yields **no** `jwt` block and the security-off e2e suite stays green — proving P6 is additive and opt-in.

The exact EG `spec.jwt` field shape that produces (a)+(b)+(c), the EG version, the Keycloak token recipe, and every command/output transcript are recorded in `impl/learnings/P6-*.md` and summarised in `REPORT.md`.

## Numbered TODOs

Each task is self-contained: make the change, run the listed validation, then commit with a comprehensive functional message.

1. **Operator user-auth config.** In `operator/pkg/security/config.go` add `UserIssuer`, `UserAudience`, `UserJWKSURI` fields + env constants (`SECURITY_USER_AUTH_ISSUER` / `_AUDIENCE` / `_JWKS_URI`), read them in `GetConfig()`, and add `JWTEnabled()` plus JWKS-resolution helpers (explicit URI, else derived from issuer per the Keycloak/AIB rules above). Do **not** alter `IsOperational()`. Extend `config_test.go`: assert env parsing, `JWTEnabled()` true (agent-only, user-only, both) and false (neither), and JWKS resolution (explicit vs derived for both issuers).
   **Validate**: `cd operator && go test ./pkg/security/... && make test-unit`; `gofmt -l pkg/security` empty; `go vet ./pkg/security/...`.

2. **SecurityPolicy `jwt_authn` providers.** Extend `constructSecurityPolicy` in `securitypolicy.go` to emit `spec.jwt.providers` (agent provider required, extracting from `x-agent-authorization` with `valuePrefix: "Bearer "`; user provider emitted only when `UserIssuer` set, extracting from `Authorization`, with `audiences`), each with `claimToHeaders`, alongside the unchanged `extAuth`, gated on `JWTEnabled()`. Add `securitypolicy_test.go` cases: both providers rendered with correct issuer/jwks/extractFrom/audience/claimToHeaders when both issuers set; **only** the agent provider when no user issuer; **no** `jwt` block when `!JWTEnabled()`; `extAuth` block unchanged in all cases.
   **Validate**: `go test ./pkg/security/... && make test-unit`; `make manifests generate` clean (SecurityPolicy is an external CRD, unstructured — no drift expected).

3. **Operator chart user-auth wiring.** Add the `security.userAuth` block to `operator/chart/values.yaml` and render `SECURITY_USER_AUTH_*` in `templates/operator-configmap.yaml` (mirror the `agentAuth` block, only-when-set).
   **Validate**: `helm template operator/chart --set security.agentAuth.extAuthzUrl=svc:9002 --set security.userAuth.issuer=http://kc/realms/kaos --set security.userAuth.audience=kaos` shows the three env vars; with the block absent they do not render; `helm lint operator/chart`.

4. **CLI Keycloak install + realm bootstrap + userAuth wiring.** Add `_install_keycloak` + `_bootstrap_keycloak_realm` + `_default_user_auth_issuer` to `install.py`; extend `_build_auth_operator_args` with the `security.userAuth.*` `--set` args; add `--user-auth/--no-user-auth`, `--keycloak-namespace`, `--keycloak-chart-path`, `--user-auth-issuer`, `--user-auth-audience` in `system/__init__.py` and thread into `install_command`; under `--auth-enabled` (user-auth on) install Keycloak + bootstrap the realm + wire `userAuth`.
   **Validate**: extend `kaos-cli/tests/` dry-run/YAML-validation tests to assert (a) the Keycloak helm install args appear, (b) the `security.userAuth.*` operator `--set` wiring appears, (c) `--no-user-auth` omits all of it; `cd kaos-cli && source .venv/bin/activate && python -m pytest tests/ -v && make lint`.

5. **Programmatic user-token helper.** Add a reusable non-interactive token-minting helper under `./tmp/security/` that fetches a Keycloak user access token via the password/client-credentials grant against the bootstrapped realm.
   **Validate**: against the local Keycloak it returns a verifiable JWT whose `iss` matches `userAuth.issuer` and `aud` includes the configured audience (decode-and-assert, no network mock); record the recipe in `impl/learnings/P6-*.md`.

6. **Live installer-driven manual end-to-end validation + provider-shape lock-in.** This is a manually-executed, captured run (per Design §E), not just a test assertion. Steps:
   - **(i) Install via the real CLI:** `kaos system install --gateway-enabled --metallb-enabled --auth-enabled …` on local KIND (`kind-kaos-e2e`), exercising the new Keycloak install + realm bootstrap + `userAuth` operator wiring. Capture full output under `./tmp/`.
   - **(ii) Verify the cluster is up:** `kubectl get pods -A` (Keycloak, AIB, sync-service, operator, Envoy Gateway, sample workloads all Running/Ready); `kubectl get securitypolicy -A -o yaml` shows the generated `spec.jwt.providers` (agent+user) and unchanged `extAuth`; confirm EG image is v1.4.6; port-forward the gateway (`svc/envoy-gateway 8888:80`, `GATEWAY_URL=http://localhost:8888`).
   - **(iii) Run real commands against deployed components:** deploy a sample `Agent → MCPServer` with a granted edge; drive real gateway requests (curl with T5-minted tokens; suppress to `./tmp/null`) and assert the five-case matrix on observed status codes: (a) user+actor → 200; (b) actor-only, no user → 200; (c) invalid user → 401 (jwt_authn); (d) missing/invalid actor → 401/403; (e) granted vs ungranted edge → allow vs deny (ext_authz after jwt_authn). Cross-check Envoy access logs, the AIB Check decision, and the agent credential Secret. Optionally also drive via `kaos` CLI verbs that traverse the gateway.
   - **(iv) Default-off contract:** a second install without `--auth-enabled` (or `--no-user-auth`) renders no `jwt` block and the security-off e2e suite stays green.
   - Lock in the exact EG `spec.jwt` field shape that yields (a)+(b)+(c); record it, the EG version, the Keycloak token recipe, and every command/output transcript.
   **Validate**: the five-case matrix passes against the live cluster; default-off install adds nothing; all transcripts captured under `./tmp/` and summarised for `impl/learnings/P6-*.md` + `REPORT.md`.

7. **Docs, progress/learnings, PR, CI, REPORT.** Copy this plan to `kaos-ai-docs/.../plan/P6-gateway-user-authentication.md`; write `impl/progress/P6-*.md` + `impl/learnings/P6-*.md` (EG version + final `spec.jwt` shape + Keycloak token recipe + optionality contract). Push `feat/gateway-user-authentication`, open the stacked PR into `feat/sync-service-reconciliation`, dispatch `go-tests`/`python-tests`/`e2e-tests` via `workflow_dispatch --ref feat/gateway-user-authentication`, confirm CI green. Write the gitignored `REPORT.md` (P0–P6 status + this work) and post it as a PR comment (do **not** commit it).
   **Validate**: CI green on the branch (Go, Python, security-off E2E); REPORT.md posted; REPORT.md remains untracked (`git check-ignore REPORT.md`).

## Validation per task (summary)

- **Operator (T1–T2)**: `go test ./pkg/security/...` + `make test-unit` + `make manifests generate` (no drift); `gofmt`/`go vet`.
- **Chart (T3)**: `helm template` (env present when set, absent when not) + `helm lint`.
- **CLI (T4)**: `pytest tests/` (dry-run YAML assertions) + `make lint`.
- **Token helper (T5)**: decode-and-assert iss/aud against live Keycloak.
- **Combined e2e (T6)**: live **installer-driven** manual run on local KIND — install via `kaos system install --auth-enabled`, verify all components Running/Ready, drive real gateway requests through deployed components for the five-case matrix, cross-check Envoy/AIB/Secret state, confirm default-off install adds nothing; security-off suite stays green; transcripts captured under `./tmp/`.
- **CI (T7)**: dispatch the three workflows on the branch; the full combined-authn path is **local-KIND only** (unpublished broker) and documented in `REPORT.md`.

## Commit / PR strategy

- `feat/gateway-user-authentication` stacked off `feat/sync-service-reconciliation` (P5 tip); **one comprehensive, functional commit per TODO**; PR into `feat/sync-service-reconciliation`; keep CI green; Copilot co-author trailer on KAOS commits (kaos-ai-docs commits: **no** trailer).
- Push under the `axsaucedo` gh account; keep the commit author as the repo default; restore the EMU account afterwards.
- `REPORT.md` gitignored; contents posted as a PR comment.

## Out of scope (later phases)

`ext_proc` token exchange and user-delegated third-party grants (**P7**); `spec.security.id` CRD identity override (**P8**); externally-managed Keycloak / custom-issuer granular override flags (added on demand per ADR-KAOS-008, beyond the single `--auth-enabled` switch); interactive browser SSO/login UX (only the non-interactive token path is automated); fine-grained user RBAC/roles beyond presence + issuer + audience validation (later authorization-policy work, ADR-KAOS-005); NetworkPolicy/ClusterIP-bypass prevention and gateway TLS (**P4**, resequenced after P11); SDK changes (user `Authorization` forwarding already landed in P1); grant-ownership / consent-driven sync model (followup ADR, P10–P12).
