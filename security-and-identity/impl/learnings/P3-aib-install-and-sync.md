# P3 — End-to-end wiring and install (learnings)

**Phase**: P3 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Date**: 2026-06-21
**Context**: assembling the broker install, the KAOS→broker sync service, operator credential mounting, and the CLI `--auth-enabled` path into a working end-to-end MVP on local KIND.

## Key findings

### The credential Secret name must be derivable on both sides from the KAOS agent name

The operator mounts a per-agent credential Secret into the agent pod, and the sync service writes that Secret — but the two never coordinate at runtime. They agree only by convention: the Secret is named `<credentialSecretPrefix>-<agentName>` (e.g. `kaos-aib-researcher`) and lives in the **agent's own namespace**. This works because the KAOS agent name is known to both: the operator reconciles the Agent CR and the sync service lists Agent CRs. Crucially the name is **not** keyed on the broker's internal agent UUID — the operator can never know that UUID, so any naming scheme based on it would be unmountable. The prefix is a single shared setting (`security.agentAuth.credentialSecretPrefix` on the operator, `sync.credentialSecretPrefix` on the sync chart) and the CLI sets both from one value so they cannot drift.

### Credential env must use optional Secret references so pods start before the Secret exists

There is a chicken-and-egg ordering: the operator may create the agent Deployment before the sync service has minted and written the credential Secret. If the pod referenced the Secret as a required `secretKeyRef`, the kubelet would refuse to start the container until the Secret appeared. The agent reconciler therefore injects `AIB_CLIENT_ID`/`AIB_CLIENT_SECRET` as **optional** secret references (`optional: true`): the pod starts immediately, the env vars are simply absent until the Secret exists, and they populate on the next pod restart after the sync service writes them. `AIB_ACTOR` (the agent's stable external identity `kaos://agent/<ns>/<name>`) and `AIB_TOKEN_ENDPOINT` (derived from the issuer) are plain values the operator can always compute, so they are set unconditionally when mounting is enabled.

### Credential mounting is gated on the same operational signal as gateway enforcement, plus a prefix

`security.Config.CredentialMountingEnabled()` is `IsOperational() && credentialSecretPrefix != ""`, i.e. it requires both an access-check URL (the existing P2 "security is on" signal) and a credential prefix. This keeps the default-off contract intact: with no security config the agent reconciler appends no new env and existing deployments are byte-for-byte unchanged, so the operator envtest/e2e suites stay green without modification. The token endpoint is `issuer + /oauth2/token`; when no issuer is set, `AIB_TOKEN_ENDPOINT` is simply omitted (credentials are still mounted).

### Idempotent minting is essential to avoid credential churn

The reconcile loop runs periodically over all agents. `mint_credentials` always creates a fresh client secret on the broker, so the loop must only mint when the agent's Secret does **not** already carry a `client_id`; otherwise every pass would rotate every agent's secret and invalidate live tokens. The guard lives in the reconcile logic (mint only when the Secret lacks a client id), and the broker record itself is created idempotently via create-or-get (POST first, fall back to a list-scan match). The reconcile logic is written against narrow protocols (a Secret store and a broker admin client) with no I/O, so it is fully unit-tested with fakes.

### The broker chart's key fields have an asymmetric base64 contract

Installing the broker on the memory backend requires two 32-byte keys, and the chart treats them differently. `broker.thirdPartyOauth2.jweSigningKey` is run through Helm's `b64enc` before being placed into the Secret `data`, so it must be supplied as a **single** base64 encoding of the 32 raw bytes. `broker.encryption.memory.rawKey` is placed **directly** into Secret `data` (which is itself base64), so it must be supplied **double**-base64-encoded. Both resolve to the same 32 raw bytes the broker expects as a base64 env value. The `jweSigningKeyBase64` variant writes straight into `data` and would need double encoding — it is avoided in favour of `jweSigningKey`. The committed dev values preset encodes both correctly so the dev install is reproducible; this is documented in ADR-AIB-000.

### The broker is unpublished, so the full auth e2e is local-KIND only

The broker has no public image or chart, so the complete authentication path cannot run in KAOS GitHub Actions. The split adopted: KAOS CI runs the operator unit/envtest, the CLI dry-run tests, the new sync unit tests, and the existing security-off e2e suite (which must stay green); the full auth e2e (broker + sync + operator + sample agent, allow/deny through the decision) is validated on the local KIND cluster and documented. The CLI `--auth-enabled` flag accordingly supports a local broker chart path and local/dev image overrides for the sync service, rather than assuming published artifacts.

## Decisions carried forward

- Sync stays Python (reusing the validated prototype); a Go rewrite for native watch/extraction is a later phase.
- Credential mounting covers agent pods only (the actor is always an agent); MCPServer-as-caller is a follow-up.
- Keycloak/user-auth, NetworkPolicy/ClusterIP-bypass prevention, gateway TLS, and `ext_proc` token exchange remain deferred to their respective later phases.
