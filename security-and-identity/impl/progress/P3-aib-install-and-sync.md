# P3 — End-to-end wiring and install (progress)

**Phase**: P3 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P3-aib-install-and-sync.md`](../../plan/P3-aib-install-and-sync.md)
**Status**: Complete — the install-and-sync MVP is wired and validated end to end on local KIND.
**Date**: 2026-06-21
**Tracking issue**: axsaucedo/kaos#231
**PR**: axsaucedo/kaos#234 (stacked onto the gateway ext_authz branch)

## Outcome

The agent-authentication components are now installable and wired together: the identity broker installs on a memory backend with a committed dev preset, a KAOS→broker sync service projects KAOS resources into the broker and provisions per-agent credential Secrets, the operator mounts those credentials into agent pods, and a single CLI flag (`kaos system install --auth-enabled`) wires the operator to the broker and deploys the sync service. The end-to-end decision path was validated live: a synced agent's granted edge is allowed and an ungranted edge is denied, with the credential Secret named by the same convention the operator mounts.

## Deliverables

| Area | Deliverable |
|---|---|
| Broker foundation | Chart defaults to `memory`; committed dev values preset (JWE/encryption/preauth keys); repeatable host-arch image build + `kind load` recipe. |
| Sync projection | `sync-service/kaos_sync/projection.py` — pure, tested mapping of KAOS Agent/MCPServer/ModelAPI → synthetic services, permission sets, local-client agents, requested edges. |
| Sync runtime | `config.py`, `aib_client.py`, `k8s.py`, `reconcile.py`, `main.py` — periodic reconcile loop minting per-agent credentials into `kaos-aib-<agent>` Secrets, idempotent (mints only when the Secret lacks a client id). |
| Sync packaging | `Dockerfile` + Helm chart (Deployment, ServiceAccount, cluster RBAC: read agents/mcpservers/modelapis, write Secrets). |
| Operator mounting | `security.agentAuth.issuer` + `credentialSecretPrefix`; agent reconciler injects the agent's broker identity, credentials (optional secret refs), and token endpoint, gated and default-off. |
| CLI | `kaos system install --auth-enabled` wires the operator security values and optionally installs the broker (local chart) and deploys the sync service, with namespace-derived defaults and overrides. |
| CI | Sync service unit tests + black check added to the Python test workflow. |

## Validation

- **Broker on KIND**: `helm install` of the broker chart (memory backend, dev preset) comes up `1/1`; broker `just check` + `just test` green.
- **Sync unit tests**: projection (6) + reconcile (6) green; black clean.
- **Operator**: `pkg/security` unit tests + a controller unit test asserting credential env is injected when configured and absent when off; `go build ./...` clean; `helm template` renders the new env keys only when enabled.
- **CLI**: dry-run/unit tests for the endpoint defaults, operator value wiring, and end-to-end helm argument construction; full `kaos-cli` suite green.
- **End-to-end (local KIND, gitignored `./tmp/security/` harness)**: sync projects the sample resources into the live broker, mints the per-agent credential Secret `kaos-aib-researcher`, mints an actor token, and the access-check honours the synced edges — `github` (granted) allowed, `slack` (ungranted) denied.
- **Sync chart on KIND**: the sync pod runs `1/1` in the broker namespace and reconciles against the broker admin API.

## Notes

- The broker is unpublished (no public image/chart), so the full auth e2e runs on local KIND only and is documented rather than run in KAOS GitHub Actions. KAOS CI runs the operator, CLI, and sync unit suites plus the existing security-off e2e suite.
- Sync is Python now (reusing the validated prototype); a Go rewrite for native watch/extraction is deferred. Credential mounting covers agent pods only. Keycloak/user-auth, NetworkPolicy/TLS, and `ext_proc` token exchange are deferred to later phases.
