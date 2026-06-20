# ADR-010: AIB integration and synchronization architecture

**Status**: Accepted
**Date**: 2026-06-20

---

## Decision

KAOS will integrate with AIB as an **externally managed broker service**.

KAOS will not install, upgrade, own, or lifecycle-manage AIB. AIB should be installed through AIB-owned distribution mechanisms, primarily the AIB Helm chart or another external platform path.

KAOS will provide **configuration support** for using an existing AIB installation. The primary KAOS-side UX may be a CLI/configuration path such as:

```text
kaos system install --aib-enabled \
  --aib-base-url ... \
  --aib-admin-url ... \
  --aib-admin-credentials-secret ...
```

This configures KAOS runtimes, operator settings, SDK environment variables, and credential references to use AIB. It does **not** install AIB.

KAOS-to-AIB synchronization will not be embedded into KAOS core and will not be embedded into AIB core. Automatic synchronization may be provided by a **lightweight external synchronization service** that watches KAOS resources, computes desired AIB records, calls AIB admin APIs, and reports drift/status.

In this ADR, "controller" means reconciliation behavior:

```text
watch/list KAOS resources -> compute AIB desired records -> call AIB admin APIs -> report drift/status
```

It does not require a Go/Kubebuilder operator, new CRDs, or code inside the KAOS operator. The sync service may be implemented in Go, Python, or any language with Kubernetes watch support.

The synchronization service is responsible for:

1. **Discovery**
   - Watch KAOS Agent, MCPServer, and ModelAPI resources.
   - Discover requested access edges from Agent specs.
   - Read AIB endpoint/configuration from its own configuration or KAOS CLI-generated configuration.

2. **Identity projection**
   - Compute canonical KAOS logical IDs from [ADR-001](./ADR-001-identity-model-and-source-of-truth.md).
   - Create or update AIB records using stable `external_id` values.
   - Preserve AIB records across Kubernetes delete/recreate when the logical identity is intentionally stable.

3. **Requested-edge projection**
   - Mirror CRD topology as requested access edges.
   - Keep requested edges separate from approved platform/resource grants.
   - Avoid auto-approving access because an Agent references an MCPServer, ModelAPI, or sub-agent.

4. **Bootstrap mapping**
   - For the current AIB model, optionally encode early KAOS resource access through a synthetic internal service and PermissionSet scopes.
   - Mark this as compatibility encoding, not the target platform/resource grant model.

5. **AIB configuration reconciliation**
   - Ensure required AIB agent records, third-party service records, and PermissionSets exist when KAOS declares or references them.
   - Optionally generate and rotate agent client credentials through AIB admin APIs.
   - Store resulting client credentials in Kubernetes Secrets for the relevant KAOS workload, when credential management is enabled.

6. **Status and drift reporting**
   - Report synchronization state through service logs, metrics, and optional Kubernetes annotations/status integration.
   - Report AIB unreachable, AIB record drift, missing credentials, stale external IDs, and unsupported requested edges.
   - Never silently fall back to insecure behavior when synchronization fails.

The sync service may live in a separate repository, an AIB-adjacent integration repository, or initially as documented sample code. It should not make KAOS own AIB lifecycle and should not make AIB itself KAOS-specific.

---

## Context

[ADR-001](./ADR-001-identity-model-and-source-of-truth.md) establishes that KAOS owns logical resource identity and topology, while AIB can mirror KAOS identities through `external_id`.

[ADR-004](./ADR-004-aib-responsibility-boundary.md) establishes that KAOS CRDs define requested access edges, and that AIB may store the broker-side grants and records used for authorization and delegated-token flows.

[ADR-009](./ADR-009-aib-python-sdk-design.md) establishes that SDK/native calls are the first integration path for runtime AIB use.

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

This provides a local AIB end-to-end development topology. ExtProc remains a separate deployment unit and is deferred from the SDK-first baseline by [ADR-002](./ADR-002-enforcement-topology.md).

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

The sync service watches KAOS resources and mirrors desired AIB records. It may be a simple Deployment with Kubernetes watch permissions and AIB admin credentials. A full Kubernetes operator with CRDs and status resources is not required for the initial architecture.

### Runtime integration

Runtime calls continue to follow ADR-009:

```text
Agent / MCPServer runtime
  -> AIB SDK/client
  -> AIB token exchange / access checks
```

ExtProc remains optional and later-stage:

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
- Preserves CLI simplicity by giving KAOS an `--aib-enabled` style configuration path.

### Negative

- Users must install and operate AIB separately.
- Full automation requires another component if automatic synchronization is desired.
- Sync status integration into KAOS resources is weaker unless explicitly added.
- Version compatibility must be managed across KAOS CRDs, the external sync service, and AIB admin APIs.
- Bootstrap encoding may be needed until AIB has first-class KAOS platform/resource grant APIs.

### Risks

- Users may assume `--aib-enabled` installs AIB unless CLI docs and validation are explicit.
- Insecure AIB evaluation defaults such as memory storage could be used accidentally if KAOS does not document production expectations.
- A sync service with broad Kubernetes watch permissions and AIB admin credentials becomes security-sensitive.
- If requested edges are mistaken for approved grants, synchronization could become over-permissive.

---

## Final decision

1. KAOS does not install, upgrade, or lifecycle-manage AIB.
2. AIB is installed externally, normally through the AIB Helm chart or another AIB-owned distribution path.
3. KAOS provides CLI/runtime/operator configuration hooks for using an existing AIB installation.
4. `--aib-enabled` style UX configures KAOS to use AIB; it does not install AIB.
5. Automatic KAOS-to-AIB synchronization lives outside KAOS core as a lightweight external sync service.
6. The external sync service may be implemented in Go, Python, or any language with Kubernetes watch support.
7. The external sync service does not need to be a full Kubernetes operator with CRDs.
8. The sync service watches KAOS resources, computes desired AIB records, calls AIB admin APIs, and reports drift/status.
9. CRD references are requested access edges, not approved grants.
10. AIB remains authoritative for user-delegated grants, third-party sessions, token exchange, and target platform/resource grants once the AIB model supports them.
11. Bootstrap encoding through synthetic services or PermissionSets is allowed only as an explicit temporary compatibility layer.
12. ExtProc remains optional and later-stage; SDK/native calls remain the initial runtime integration path.
