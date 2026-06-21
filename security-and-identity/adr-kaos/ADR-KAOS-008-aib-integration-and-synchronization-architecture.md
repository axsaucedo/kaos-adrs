# ADR-KAOS-008: AIB integration and synchronization architecture

**Status**: Accepted
**Date**: 2026-06-20

---

## Decision

KAOS separates **AIB lifecycle** from **AIB integration**, and owns only the latter.

### Lifecycle (KAOS does not own it)

KAOS does not own, upgrade, or lifecycle-manage AIB or the IdP (Keycloak) as part of its reconciliation. Their storage, keys, migrations, and upgrades are managed externally through their own Helm charts / operators. Production deployments are expected to run externally-managed AIB and Keycloak.

### Integration (KAOS owns it, via the CLI, like other platform integrations)

KAOS configures itself to **use** AIB and Keycloak, following the same flow as other `kaos system install` integrations (otel, gateway, metallb). A single `--auth-enabled` flag is the convenience path: it installs the Keycloak and AIB Helm charts, deploys the KAOS→AIB sync service, and wires the operator security config (`security.tls` / `security.userAuth` / `security.agentAuth`, see [ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md)):

```text
# Convenience: install Keycloak + AIB + sync service and wire operator security config
kaos system install --auth-enabled
```

`--auth-enabled` activates the whole authentication/authorization stack as one switch. Granular override flags — pointing at externally-managed Keycloak/AIB, custom issuers, or custom `ext_authz`/`ext_proc`/admin endpoints — are a deliberate **future addition**, added only when a deployment needs them; they are not required for the initial integration. Installing the charts as a convenience is **not** KAOS taking ownership of their lifecycle — it is a bootstrap, and operators may disable it and manage AIB/Keycloak themselves.

### Synchronization (lightweight external service)

KAOS-to-AIB synchronization is not embedded into KAOS core and not into AIB core. It is a **lightweight external synchronization service** that watches KAOS resources, computes desired AIB records, calls AIB admin APIs, and reports drift/status:

```text
watch/list KAOS resources -> compute AIB desired records -> call AIB admin APIs -> report drift/status
```

It does not require a Go/Kubebuilder operator, new CRDs, or code inside the KAOS operator, and may be implemented in any language with Kubernetes watch support. The AIB admin URL/credentials live in this sync-service config (not in the operator/gateway enforcement config).

The synchronization service is responsible for: 

1. **Discovery**
   - Watch KAOS Agent, MCPServer, and ModelAPI resources.
   - Discover requested access edges from Agent specs.
   - Read AIB endpoint/configuration from its own configuration or KAOS CLI-generated configuration.

2. **Identity projection**
   - Compute canonical KAOS logical IDs from [ADR-KAOS-001](./ADR-KAOS-001-identity-model-and-source-of-truth.md).
   - Create or update AIB records using stable `external_id` values.
   - Preserve AIB records across Kubernetes delete/recreate when the logical identity is intentionally stable.

3. **Requested-edge projection**
   - Mirror CRD topology as requested access edges.
   - Keep requested edges separate from approved platform/resource grants.
   - Avoid auto-approving access because an Agent references an MCPServer, ModelAPI, or sub-agent.

4. **Bootstrap mapping**
   - For the current AIB model, optionally encode early KAOS resource access through a synthetic internal service and PermissionSet scopes.
   - Mark this as compatibility encoding, not the target platform/resource grant model.

5. **Agent identity and credential provisioning**
   - Ensure required AIB agent records, third-party service records, and PermissionSets exist when KAOS declares or references them.
   - Generate and rotate **per-agent AIB client credentials** through the AIB admin API for each identity-bearing caller. This is **required when security is enabled** (it is how an agent authenticates as the actor; see [ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md)), not optional.
   - Write the resulting client credentials into per-agent Kubernetes Secrets (named by `credentialSecretPrefix`, e.g. `kaos-aib-<agentid>`). The **operator mounts** these Secrets into the agent/MCPServer pods ([ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md)); Kubernetes keeps a pod `Pending` until its Secret exists, which orders provisioning naturally.

6. **Status and drift reporting**
   - Report synchronization state through service logs, metrics, and optional Kubernetes annotations/status integration.
   - Report AIB unreachable, AIB record drift, missing credentials, stale external IDs, and unsupported requested edges.
   - Never silently fall back to insecure behavior when synchronization fails.

In summary, the sync service projects, at a high level: KAOS logical identities (`external_id`), requested access edges (kept distinct from approved grants), third-party services and PermissionSets, **per-agent client credentials** (into Secrets), and drift/status. It should not make KAOS own AIB lifecycle and should not make AIB itself KAOS-specific.

### Packaging and distribution (CLI-installed)

Although the sync service is **not** part of KAOS core (it is a separate process, not the operator, and holds AIB admin credentials), it is part of the **KAOS install experience**: `kaos system install
--auth-enabled` deploys it alongside the Keycloak/AIB charts so users get a working integration without
assembling components by hand. Packaging follows a start-simple-then-extract path:

1. **Now — same repo, CLI-deployed.** The sync service lives in the KAOS repository (e.g. a small Go or Python Deployment with its own image and a minimal Helm chart/manifest) and is rendered/applied by the CLI under `--auth-enabled`. This keeps versioning, CI, and release in lockstep with KAOS while the contract with AIB stabilizes.
2. **Later — own repository.** Once the AIB admin contract and the sync logic are stable, the service can be extracted into its own repository (or an AIB-adjacent integration repo) and consumed by the CLI as a versioned external chart/image, exactly as KAOS already consumes Keycloak and AIB.

Either way the CLI is the integration point: it installs the chart and wires the sync-service config (AIB admin URL/credentials, watch scope). Operators may disable the bundled sync service and run their own. This deliberately avoids embedding the sync logic into the operator (see Option B) while still giving a one-command install.

---

## Context

[ADR-KAOS-001](./ADR-KAOS-001-identity-model-and-source-of-truth.md) establishes that KAOS owns logical resource identity and topology, while AIB can mirror KAOS identities through `external_id`.

[ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md) establishes that KAOS CRDs define requested access edges, and that AIB may store the broker-side grants and records used for authorization and delegated-token flows.

[ADR-AIB-001](../adr-aib/ADR-AIB-001-aib-python-sdk-design.md) establishes that SDK/native calls are the baseline integration path for runtime AIB use.

The remaining architecture question is operational: whether AIB should become a KAOS-managed control-plane dependency, an embedded KAOS component, or an external service with a synchronization bridge.

AIB is operationally closer to Keycloak or an OTel collector than to a library. It has server ports, storage, migrations, keys, admin APIs, end-user APIs, optional ingress, and token-vault state. KAOS should consume it as a broker service, not absorb its lifecycle.

---

## Source facts

### AIB Docker images

Source files:

- `agentic-identity-broker/Dockerfile`
- `agentic-identity-broker/Dockerfile.migrate`
- `agentic-identity-broker/Dockerfile.extproc`
- `agentic-identity-broker/Justfile`
- `agentic-identity-broker/delivery.yaml`

AIB defines buildable container images for:

```text
agentic-identity-broker
agentic-identity-broker-migrate
agentic-identity-broker-extproc
```

The `Justfile` builds and pushes broker, migration, and ExtProc images as multi-architecture images. The delivery pipeline builds and pushes them with:

```text
IMAGE_NAME="${CDP_REGISTRY}/infosec/agentic-identity-broker"
```

The checked-in Helm chart defaults to local image names, so KAOS must not assume public image coordinates unless they are explicitly configured or published by AIB.

### AIB Kubernetes and Helm distribution

Source files:

- `agentic-identity-broker/charts/agentic-identity-broker/Chart.yaml`
- `agentic-identity-broker/charts/agentic-identity-broker/values.yaml`
- `agentic-identity-broker/charts/agentic-identity-broker/templates/deployment.yaml`
- `agentic-identity-broker/charts/agentic-identity-broker/templates/service.yaml`
- `agentic-identity-broker/charts/agentic-identity-broker/templates/job-migrate.yaml`
- `agentic-identity-broker/charts/agentic-identity-broker/templates/ingress-enduser.yaml`
- `agentic-identity-broker/charts/agentic-identity-broker/templates/ingress-admin.yaml`

AIB ships a Helm chart:

```text
name: agentic-identity-broker
version: 0.1.0
appVersion: 0.1.0
```

The chart includes:

- Deployment for the broker.
- Service exposing end-user and admin ports.
- Optional Ingress for end-user and admin APIs.
- Optional HPA and PodDisruptionBudget.
- ServiceAccounts.
- ConfigMap-generated `config.yaml`.
- JWE and encryption Secrets.
- Optional PostgreSQL storage.
- Optional Zalando PostgreSQL Operator integration.
- Migration Job for PostgreSQL mode.

Default ports:

```text
end-user API: 8000
admin API:    14000
```

Default storage:

```text
storage.type: memory
```

Production-like AIB installations require persistent PostgreSQL storage, migrations, signing/encryption keys, admin authentication, end-user authentication, public URLs, network boundaries, observability, and backup/restore posture for token-vault state. These are AIB installation responsibilities, not KAOS operator responsibilities.

### AIB local distribution and gateway path

Source files:

- `agentic-identity-broker/docker-compose.yml`
- `agentic-identity-broker/config.docker.yaml`
- `agentic-identity-broker/config.extproc.docker.yaml`
- `agentic-identity-broker/mocks/agentgateway/config.yaml`

The Docker Compose setup runs:

- identity broker,
- frontend,
- mock upstream OAuth2 service,
- mock third-party OAuth2 service,
- mock sample agent,
- ExtProc token exchange service,
- mock MCP server,
- agentgateway.

This provides a local AIB end-to-end development topology. ExtProc runs as a separate deployment unit at the gateway, per [ADR-KAOS-002](./ADR-KAOS-002-enforcement-topology.md).

### AIB admin API surfaces useful for synchronization

Source files:

- `agentic-identity-broker/api/admin/openapi.yaml`
- `agentic-identity-broker/api/enduser/openapi.yaml`

AIB exposes admin operations for:

- agents: list, create, get, update, delete,
- third-party services: list, create, get, update, delete,
- permission sets: create, list, get, update, delete,
- agent client credentials: generate, get, revoke,
- signing keys: create, list, promote, delete.

AIB exposes end-user operations for:

- user profile,
- agent delegations,
- agent details,
- grants,
- third-party sessions,
- OAuth2 flow initiation/callback,
- token exchange,
- JWKS and OAuth2 metadata.

Current AIB does not expose a KAOS-specific resource graph, first-class KAOS platform/resource grants, or a KAOS resource request/approval queue. The external sync service must therefore either:

1. use bootstrap encoding through existing AIB agents, services, and PermissionSets; or
2. wait for first-class AIB platform/resource grant APIs.

### KAOS source-of-truth resources

Source files:

- `operator/api/v1alpha1/agent_types.go`
- `operator/api/v1alpha1/mcpserver_types.go`
- `operator/api/v1alpha1/modelapi_types.go`

KAOS owns CRDs for:

- Agent,
- MCPServer,
- ModelAPI.

Agent specs reference:

- `spec.modelAPI`,
- `spec.mcpServers`,
- `spec.agentNetwork`.

The synchronization source of truth is the Kubernetes API via KAOS CRDs. AIB should not become the source of truth for whether a KAOS Agent, MCPServer, or ModelAPI exists.

---

## Architecture

### External AIB installation

AIB installation is external to KAOS:

```text
AIB Helm chart / platform install
  -> AIB broker Deployment
  -> AIB PostgreSQL / token vault
  -> AIB admin and end-user endpoints
```

KAOS consumes the resulting endpoints and credentials:

```text
KAOS CLI/config
  -> operator/runtime settings
  -> SDK env vars
  -> Kubernetes Secret refs
  -> Agent/MCPServer runtime AIB client configuration
```

KAOS documentation and CLI validation should make required AIB production settings explicit, but KAOS does not render or own AIB manifests.

### External synchronization service

Automatic synchronization is optional:

```text
KAOS Kubernetes API
  -> external AIB sync service
  -> AIB admin API
```

The sync service watches KAOS resources and mirrors desired AIB records. It may be a simple Deployment with Kubernetes watch permissions and AIB admin credentials. A full Kubernetes operator with CRDs and status resources is not required for the target architecture.

### Runtime integration

Runtime calls continue to follow [ADR-AIB-001](../adr-aib/ADR-AIB-001-aib-python-sdk-design.md):

```text
Agent / MCPServer runtime
  -> AIB SDK/client
  -> AIB token exchange / access checks
```

ExtProc remains optional as part of Gateway resource-boundary deployments:

```text
Gateway / ExtProc
  -> AIB token exchange
  -> protected upstream service
```

---

## Annex: Alternatives considered

### Option A: KAOS installs and manages AIB

KAOS would install AIB as an optional control-plane dependency, using the AIB Helm chart or rendered manifests.

Rejected.

This would make KAOS responsible for an external broker's lifecycle, storage, migrations, keys, ingress, image coordinates, and upgrade compatibility. It would also couple KAOS releases to AIB operational concerns. KAOS should instead configure itself to use an externally installed AIB.

### Option B: Embed synchronization into the KAOS operator

The KAOS operator would watch KAOS resources and call AIB admin APIs directly.

Rejected for the target architecture.

This provides strong KAOS status integration, but it makes KAOS core own AIB-specific reconciliation, drift behavior, credentials handling, and AIB API versioning. The integration is useful but optional, so it should start as an external sync service.

### Option C: Embed synchronization into AIB

AIB would include a Kubernetes watcher or plugin that watches KAOS CRDs directly.

Rejected.

This couples AIB to KAOS CRDs and Kubernetes semantics, making AIB less orchestrator-neutral. AIB should remain the broker and grant/token authority, not the owner of KAOS topology.

### Option D: Manual AIB administration only

Admins would manually create all AIB agents, services, PermissionSets, and credentials.

Deferred as an acceptable fallback but not the target.

Manual administration is useful for simple or early deployments, but it does not scale well as KAOS resources change. A lightweight external sync service keeps automation available without pulling AIB lifecycle into KAOS.

---

## Consequences

### Positive

- Keeps KAOS core and operator simpler.
- Keeps AIB lifecycle, chart, storage, keys, and upgrades owned by AIB/platform operators.
- Allows AIB integration without coupling KAOS releases to AIB releases.
- Allows a lightweight sync implementation in Go, Python, or another Kubernetes-watch-capable runtime.
- Keeps AIB orchestrator-neutral.
- Preserves CLI simplicity by giving KAOS a single `--auth-enabled` configuration path.

### Negative

- Users must install and operate AIB separately.
- Full automation requires another component if automatic synchronization is desired.
- Sync status integration into KAOS resources is weaker unless explicitly added.
- Version compatibility must be managed across KAOS CRDs, the external sync service, and AIB admin APIs.
- Bootstrap encoding may be needed until AIB has first-class KAOS platform/resource grant APIs.

### Risks

- `--auth-enabled` bootstrap-installs AIB/Keycloak by default; CLI docs and validation must make clear KAOS does not then own their lifecycle and that external instances can be used instead.
- Insecure AIB evaluation defaults such as memory storage could be used accidentally if KAOS does not document production expectations.
- A sync service with broad Kubernetes watch permissions and AIB admin credentials becomes security-sensitive.
- If requested edges are mistaken for approved grants, synchronization could become over-permissive.

---

## Final decision

1. KAOS does not own, upgrade, or lifecycle-manage AIB or Keycloak; their storage, keys, migrations, and upgrades stay external.
2. `--auth-enabled` may **bootstrap-install** the AIB and Keycloak Helm charts and the sync service as a convenience, but this is not lifecycle ownership; operators may disable it and point at externally-managed AIB/Keycloak.
3. KAOS provides CLI/runtime/operator configuration hooks for using a bootstrapped or externally-managed AIB installation.
4. `--auth-enabled` is a single switch that activates the whole stack; granular external-instance/override flags are a future addition.
5. Automatic KAOS-to-AIB synchronization lives outside KAOS core as a lightweight external sync service.
6. The external sync service may be implemented in Go, Python, or any language with Kubernetes watch support.
7. The external sync service does not need to be a full Kubernetes operator with CRDs.
8. The sync service watches KAOS resources, computes desired AIB records, calls AIB admin APIs, and reports drift/status.
9. CRD references are requested access edges, not approved grants.
10. AIB remains authoritative for user-delegated grants, third-party sessions, token exchange, and target platform/resource grants once the AIB model supports them.
11. Bootstrap encoding through synthetic services or PermissionSets is allowed only as an explicit temporary compatibility layer.
12. ExtProc remains optional in Gateway resource-boundary deployments; SDK/native calls remain the baseline runtime integration path.
