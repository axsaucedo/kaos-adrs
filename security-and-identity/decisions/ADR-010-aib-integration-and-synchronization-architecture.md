# ADR-010: AIB integration and synchronization architecture

**Status**: Proposed
**Date**: 2026-06-20

---

## Decision area

AIB deployment, ownership, and KAOS-to-AIB synchronization.

This ADR expands the synchronization note in [ADR-004](./ADR-004-aib-responsibility-boundary.md) into a dedicated architecture decision. It covers how KAOS should integrate AIB as a deployed broker, how KAOS resources should be mirrored into AIB, and where the synchronization/control service should live.

---

## Question

How should KAOS integrate with AIB operationally and architecturally?

The decision needs to answer:

1. Is AIB a separately managed third-party service, a KAOS-managed control-plane dependency, or an embedded KAOS component?
2. Should KAOS install and lifecycle-manage AIB, or only connect to an existing AIB endpoint?
3. Should KAOS-to-AIB synchronization live inside KAOS or inside AIB?
4. What exactly does the synchronization service do beyond copying CRD records?
5. Which AIB artifacts exist today: Docker images, Kubernetes manifests, Helm chart, migration job, ExtProc image, and local development distribution?
6. What AIB features need upstream extension before the target architecture is complete?

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

The `Justfile` builds/pushes the broker, migration, and ExtProc images as multi-architecture images. The delivery pipeline builds and pushes them with:

```text
IMAGE_NAME="${CDP_REGISTRY}/infosec/agentic-identity-broker"
```

Implications:

- AIB is containerizable and intended to run as a deployable service.
- There is evidence of private-registry image publication through the delivery pipeline.
- The checked-in Helm chart defaults to local image names, so KAOS cannot assume a public production image coordinate unless that is separately published or configured.

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

Production-like storage requires PostgreSQL and migrations.

Implications:

- AIB already has a Kubernetes distribution path through Helm.
- The current chart is suitable as a deployable dependency, not only as a local development artifact.
- A production KAOS integration must configure persistent storage, signing keys, encryption keys, admin authentication, end-user authentication, public URLs, and image repository/tag values.

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

Implications:

- AIB has a local end-to-end development topology for broker + agent + MCP + ExtProc.
- ExtProc is a separate deployment unit from the main broker.
- Gateway/ExtProc integration exists, but ADR-002 keeps Gateway resource-boundary enforcement as a later hardening path rather than the SDK-first baseline.

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

Implications:

- KAOS can synchronize AIB agent records and permission sets through existing admin APIs.
- KAOS can bootstrap agent client credentials if the admin API is trusted and secured.
- AIB does not currently expose a KAOS-specific resource graph or first-class platform/resource grant model.
- AIB does not currently expose a KAOS resource request/approval queue.

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

ADR-001 and ADR-004 establish that KAOS owns logical resource identity and topology, while AIB can mirror KAOS identities through `external_id`.

Implications:

- The synchronization source of truth is the Kubernetes API via KAOS CRDs.
- AIB should not become the source of truth for whether a KAOS Agent, MCPServer, or ModelAPI exists.
- AIB records need deterministic mapping back to KAOS resources.

---

## Architecture scope

The proposed synchronization service should be broader than a record copier. It should be a **KAOS AIB Integration Controller** with these capabilities:

1. **Discovery**
   - Watch KAOS Agent, MCPServer, and ModelAPI resources.
   - Discover requested access edges from Agent specs.
   - Discover AIB endpoint/configuration from KAOS control-plane configuration.

2. **Identity projection**
   - Compute canonical KAOS logical IDs from ADR-001.
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
   - Ensure required third-party services and PermissionSets exist when KAOS declares or references them.
   - Optionally generate and rotate agent client credentials through AIB admin APIs.
   - Store resulting client credentials in Kubernetes Secrets for the relevant KAOS workload.

6. **Status and drift reporting**
   - Surface synchronization state in KAOS status conditions.
   - Report AIB unreachable, AIB record drift, missing credentials, stale external IDs, and unsupported requested edges.
   - Avoid silently falling back to insecure behavior when synchronization fails.

7. **Policy lifecycle boundary**
   - Create requested records and bootstrap artifacts.
   - Do not silently create approved grants.
   - Leave final approval semantics to AIB target platform/resource grants or an explicit KAOS admin workflow if AIB does not yet provide one.

8. **Installation integration**
   - Support connecting to an externally managed AIB.
   - Support KAOS-managed installation of AIB as an optional control-plane dependency using AIB's Helm chart or rendered manifests.
   - Keep the sync controller in KAOS because it watches KAOS CRDs and understands KAOS topology.

---

## Options

### Option A: Externally managed AIB only

KAOS would require an existing AIB endpoint and credentials. KAOS would not install AIB.

Pros:

- Clean separation from third-party service lifecycle.
- Easier for enterprise environments with central identity/security platforms.
- Similar to using an external Keycloak, OTel collector, or managed database.

Cons:

- Harder local onboarding.
- KAOS cannot provide a turnkey secure deployment.
- Users must separately install/configure AIB, database, keys, public URLs, and admin auth.
- KAOS still needs a sync controller to mirror CRDs into AIB.

### Option B: KAOS-managed AIB as an optional control-plane dependency

KAOS can install and manage AIB when enabled, while still allowing an external AIB endpoint.

Pros:

- Best fit for KAOS alpha and self-contained demos.
- Mirrors the KAOS pattern of installing platform dependencies where useful.
- Allows the operator/CLI to produce a coherent AIB configuration for Agents, MCPServers, and ModelAPIs.
- Keeps the synchronization controller in KAOS where CRD topology is available.
- Still supports production deployments that point to an externally managed AIB.

Cons:

- KAOS takes on lifecycle complexity for an external project.
- Requires version compatibility management between KAOS and AIB.
- Requires a production posture for storage, keys, admin auth, and upgrades.
- May duplicate work if AIB later ships its own Kubernetes operator.

### Option C: Embed synchronization into AIB

AIB would include a Kubernetes watcher or plugin that watches KAOS CRDs directly.

Pros:

- AIB would own its internal mapping logic.
- Could reduce KAOS-specific admin API calls.

Cons:

- Couples AIB to KAOS CRDs and Kubernetes.
- Makes AIB less orchestrator-neutral.
- Requires AIB to understand KAOS topology, status, and lifecycle semantics.
- Conflicts with ADR-004's boundary: KAOS owns resource identity and topology.

### Option D: Build a separate standalone synchronization service outside both KAOS and AIB

A third service would watch KAOS CRDs and call AIB.

Pros:

- Decoupled deployable unit.
- Could be reused outside the KAOS operator if it only depends on Kubernetes APIs and AIB APIs.

Cons:

- Adds another lifecycle component without strong benefit.
- Splits status ownership away from the KAOS operator/control plane.
- Still needs KAOS API knowledge and AIB admin credentials.
- Harder to provide a simple KAOS user experience.

---

## Tradeoffs

### Operational ownership

AIB is closer to Keycloak than to a library: it has server ports, storage, keys, admin APIs, end-user APIs, optional ingress, and migrations. Treating it as a deployed service is correct.

The open question is not whether AIB is deployable, but whether KAOS should install it by default, optionally, or never.

### Synchronization ownership

The synchronization logic is KAOS-specific because it derives identities and requested edges from KAOS CRDs. It should not be embedded into AIB unless AIB intentionally becomes KAOS-aware, which would reduce its value as a generic agent identity broker.

### Current AIB model gap

AIB can represent Agents, PermissionSets, third-party services, user grants, sessions, token exchange, and credentials. It does not yet provide the target KAOS platform/resource grant model.

Therefore the sync controller has two modes:

```text
target mode:
  sync KAOS resources and requested edges into first-class AIB resource grant APIs

bootstrap mode:
  sync KAOS resources into AIB agents/services/PermissionSets using compatibility encoding
```

Bootstrap mode must remain explicit and temporary.

### Installation modes

KAOS should not force one operational model. The integration should support:

| Mode | Description |
|---|---|
| External AIB | KAOS points to an existing AIB endpoint and credentials |
| KAOS-managed AIB | KAOS installs AIB into the KAOS control plane using configured image/chart values |
| Development AIB | KAOS or developers use local compose/Helm artifacts for testing |

### Security posture

AIB installation is not only a Deployment. Production integration requires:

- persistent PostgreSQL storage,
- migrations,
- encryption/JWE keys,
- AIB admin API authentication,
- end-user authentication,
- public URLs for OAuth2 metadata/redirects,
- network boundaries between end-user and admin APIs,
- observability and audit events,
- backup/restore posture for token-vault state.

If KAOS installs AIB, KAOS must expose these as explicit configuration rather than hiding them behind insecure defaults.

---

## Recommendation

Proposed target recommendation:

1. Treat AIB as a **deployed broker service**, not as a library and not as a Keycloak replacement.
2. Support two AIB deployment modes:
   - **external AIB**, where KAOS connects to an existing AIB endpoint;
   - **KAOS-managed AIB**, where KAOS installs AIB as an optional control-plane dependency.
3. Place the **KAOS AIB Integration Controller** in KAOS, not inside AIB.
4. Make the integration controller responsible for identity projection, requested-edge projection, bootstrap PermissionSet/service encoding, credentials reconciliation, status reporting, and drift detection.
5. Do not let CRD references auto-create approved grants.
6. Keep AIB as the authoritative broker for user-delegated grants, third-party sessions, token exchange, and target platform/resource grants once the AIB model supports them.
7. Use AIB's existing Helm chart as the initial managed-installation substrate, but do not assume public images are available until image publication is confirmed.
8. Keep ExtProc optional and later-stage; SDK/native calls remain the initial path from ADR-002 and ADR-009.
9. Treat sync service behavior as part of the KAOS control plane, with status conditions and explicit failure modes.

---

## Initial implementation implication

The initial implementation plan should likely introduce:

1. A KAOS-level AIB integration configuration, for example:

   ```text
   security.aib.mode: disabled | external | managed
   security.aib.baseURL
   security.aib.adminURL
   security.aib.adminCredentialsSecretRef
   security.aib.install.chart/image settings
   ```

2. A KAOS AIB sync/integration controller that watches:

   ```text
   Agent
   MCPServer
   ModelAPI
   ```

3. Deterministic external IDs:

   ```text
   kaos://agent/<namespace>/<name>
   kaos://mcpserver/<namespace>/<name>
   kaos://modelapi/<namespace>/<name>
   ```

4. Status conditions on KAOS resources or a dedicated integration status object:

   ```text
   AIBSynced
   AIBRecordDrift
   AIBCredentialsReady
   AIBRequestedEdgesSynced
   AIBUnsupportedGrantModel
   ```

5. Explicit bootstrap-mode documentation if using current AIB PermissionSets to encode KAOS resource access.

6. A later migration path from bootstrap encoding to first-class AIB platform/resource grants.

---

## Host questions to answer before acceptance

1. Should KAOS **install AIB by default when security is enabled**, or should it only install AIB when explicitly requested?
2. Should the KAOS-managed AIB installation reuse the upstream AIB Helm chart directly, vendor it, render it through the KAOS operator, or create a dedicated KAOS chart dependency?
3. Are public AIB images expected to exist, or should KAOS require image repository configuration for every managed install?
4. Should the AIB sync controller be part of the existing KAOS operator binary, or a separate controller Deployment managed by the operator?
5. Should KAOS introduce a first-class CRD such as `AIBIntegration`, `SecurityIntegration`, or `IdentityBroker`, or should this remain Helm/CLI configuration only?
6. In bootstrap mode, are synthetic internal services and PermissionSets acceptable, or should KAOS wait for first-class AIB platform/resource grants?
7. Should KAOS manage AIB agent client credential generation and rotation, or should credentials remain an external admin responsibility?
8. Should KAOS expose AIB admin/end-user URLs through its Gateway installation, or should AIB ingress/gateway routes remain independently configured?
9. What is the minimum production posture for KAOS-managed AIB: PostgreSQL required, memory forbidden, admin JWT required, encryption key required, backups required?
10. Should ExtProc be packaged with managed AIB immediately, or only enabled when Gateway/resource-boundary enforcement is enabled later?

---

## Deferred items

- Exact KAOS CRD/API shape for configuring AIB.
- Exact operator implementation plan.
- Exact AIB admin authentication mechanism for KAOS sync.
- Public image coordinates and release compatibility matrix.
- Bootstrap PermissionSet naming convention.
- Migration from bootstrap encoding to first-class AIB platform/resource grants.
- Whether a future AIB Kubernetes operator should replace KAOS-managed Helm installation.
- Whether AIB should upstream a generic Kubernetes sync plugin independent of KAOS.

---

## Decision status

Proposed.

This ADR should stay in the research-question format until the host answers the deployment ownership and synchronization ownership questions. Once approved, it should be converted into the accepted ADR format used by ADR-001 through ADR-009.
