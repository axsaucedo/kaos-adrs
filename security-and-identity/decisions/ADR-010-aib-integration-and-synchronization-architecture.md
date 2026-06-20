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
3. Should KAOS-to-AIB synchronization live inside KAOS, inside AIB, or in a small external integration service?
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

The proposed synchronization service should be broader than a record copier, but it should not become a large KAOS subsystem. It should be a **small external AIB synchronization service** with these capabilities:

1. **Discovery**
   - Watch KAOS Agent, MCPServer, and ModelAPI resources.
   - Discover requested access edges from Agent specs.
   - Read AIB endpoint/configuration from its own configuration or from KAOS CLI-generated configuration.

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
   - Surface synchronization state through service logs, metrics, and optionally KAOS annotations/status integration if explicitly configured.
   - Report AIB unreachable, AIB record drift, missing credentials, stale external IDs, and unsupported requested edges.
   - Avoid silently falling back to insecure behavior when synchronization fails.

7. **Policy lifecycle boundary**
   - Create requested records and bootstrap artifacts.
   - Do not silently create approved grants.
   - Leave final approval semantics to AIB target platform/resource grants or an explicit KAOS admin workflow if AIB does not yet provide one.

8. **Installation integration**
   - Support connecting to an externally managed AIB.
   - Do not install or lifecycle-manage AIB from KAOS.
   - Use KAOS CLI only to simplify KAOS-side AIB configuration, for example with an AIB-enabled flag that injects endpoints, credentials references, runtime env vars, and SDK settings.
   - Keep synchronization out of KAOS core. The service may live in an AIB-adjacent or separate integration repository because it needs KAOS CRD knowledge but should not make KAOS own AIB's lifecycle.

### What "controller" means here

In Kubernetes language, a controller is any loop that watches desired state and reconciles actual state. It does not necessarily mean a full Kubebuilder/operator project, a new CRD, or code embedded in the KAOS operator.

For this ADR, the preferred initial shape is a lightweight external synchronization service:

```text
watch/list KAOS resources -> compute AIB desired records -> call AIB admin APIs -> report drift/status
```

It can be implemented in Go, Python, or another language with Kubernetes watch support. A Go controller-runtime implementation is possible, but not required. The important property is reconciliation behavior, not the packaging style.

---

## Options

### Option A: Externally managed AIB only

KAOS would require an existing AIB endpoint and credentials. KAOS would not install AIB. AIB would be installed through its own Helm chart or another AIB-owned distribution path.

Pros:

- Clean separation from third-party service lifecycle.
- Easier for enterprise environments with central identity/security platforms.
- Similar to using an external Keycloak, OTel collector, or managed database.

Cons:

- Harder local onboarding.
- KAOS cannot provide a turnkey secure deployment.
- Users must separately install/configure AIB, database, keys, public URLs, and admin auth.
- KAOS still needs configuration hooks for SDK/runtime integration.
- A separate sync service is still needed if automatic CRD-to-AIB projection is desired.

### Option B: KAOS CLI-assisted external AIB integration

KAOS would not install AIB, but the KAOS CLI could provide an AIB-enabled installation/configuration path. For example, `kaos system install --aib-enabled` could configure KAOS runtimes, operator settings, Secrets references, and SDK environment variables to point at an externally installed AIB.

Pros:

- Keeps AIB lifecycle outside KAOS.
- Preserves a simple KAOS user experience.
- Makes AIB integration discoverable and repeatable.
- Avoids vendoring the AIB chart or coupling KAOS releases to AIB releases.
- Matches the way KAOS should integrate with other externally managed platform dependencies.

Cons:

- Users still need to install AIB separately.
- The CLI must validate required endpoint and credentials configuration.
- The CLI must avoid implying that `--aib-enabled` installs AIB.

### Option C: External AIB synchronization service

An external service would watch KAOS CRDs and call AIB admin APIs. It may live in a separate repository or an AIB-adjacent integration repository.

Pros:

- Keeps KAOS core simple.
- Avoids embedding AIB-specific reconciliation logic in the KAOS operator.
- Can evolve independently from KAOS release cadence.
- Can be deployed only by users who want automatic synchronization.
- Still allows manual AIB administration for simpler deployments.

Cons:

- Adds another component for users who want full automation.
- Needs Kubernetes API access and AIB admin credentials.
- Needs version compatibility with both KAOS CRDs and AIB APIs.
- Status integration into KAOS is weaker unless explicitly added.

### Option D: Embed synchronization into AIB

AIB would include a Kubernetes watcher or plugin that watches KAOS CRDs directly.

Pros:

- AIB would own its internal mapping logic.
- Could reduce KAOS-specific admin API calls.

Cons:

- Couples AIB to KAOS CRDs and Kubernetes.
- Makes AIB less orchestrator-neutral.
- Requires AIB to understand KAOS topology, status, and lifecycle semantics.
- Conflicts with ADR-004's boundary: KAOS owns resource identity and topology.

### Option E: Build synchronization into the KAOS operator

The KAOS operator would watch KAOS resources and call AIB admin APIs directly.

Pros:

- Strong status integration into KAOS resources.
- No additional sync Deployment.
- Direct access to KAOS reconciliation context.

Cons:

- Makes KAOS core own AIB-specific lifecycle and drift behavior.
- Couples the KAOS operator to AIB API availability and versioning.
- Increases operator complexity for an optional third-party integration.
- Makes it harder to use AIB as a separately managed platform service.

---

## Tradeoffs

### Operational ownership

AIB is closer to Keycloak than to a library: it has server ports, storage, keys, admin APIs, end-user APIs, optional ingress, and migrations. Treating it as a deployed service is correct.

The open question is not whether AIB is deployable, but whether KAOS should own its deployment. The proposed answer is no: AIB should be installed through AIB's own Helm chart or another external platform path, while KAOS only consumes its endpoints and credentials.

### Synchronization ownership

The synchronization logic is KAOS-specific because it derives identities and requested edges from KAOS CRDs. However, that does not mean it must live in KAOS core. The preferred split is:

```text
KAOS CLI/runtime/operator:
  know how to use an AIB endpoint when configured

external sync service:
  knows both KAOS CRDs and AIB admin APIs

AIB:
  remains the broker and grant/token authority
```

This keeps KAOS from lifecycle-managing AIB and keeps AIB from becoming KAOS-specific.

### Current AIB model gap

AIB can represent Agents, PermissionSets, third-party services, user grants, sessions, token exchange, and credentials. It does not yet provide the target KAOS platform/resource grant model.

Therefore the sync service has two modes:

```text
target mode:
  sync KAOS resources and requested edges into first-class AIB resource grant APIs

bootstrap mode:
  sync KAOS resources into AIB agents/services/PermissionSets using compatibility encoding
```

Bootstrap mode must remain explicit and temporary.

### Installation and integration modes

KAOS should not install AIB. The integration should support:

| Mode | Description |
|---|---|
| External AIB | AIB is installed externally, typically through the AIB Helm chart |
| CLI-assisted KAOS config | KAOS CLI enables KAOS-side AIB endpoint, credentials, and runtime settings |
| External sync service | Optional service watches KAOS CRDs and mirrors records into AIB |
| Development AIB | Developers use AIB compose/Helm artifacts for local testing |

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

Because KAOS should not install AIB, these remain AIB installation responsibilities. KAOS documentation and CLI validation should still make the required external AIB configuration explicit so users do not accidentally point KAOS at an insecure evaluation deployment.

---

## Recommendation

Proposed target recommendation:

1. Treat AIB as a **deployed broker service**, not as a library and not as a Keycloak replacement.
2. Do **not** install or lifecycle-manage AIB from KAOS.
3. Require AIB to be installed externally, normally through the AIB Helm chart or an AIB-owned distribution path.
4. Add KAOS CLI/configuration support for AIB integration, for example an AIB-enabled flag that wires KAOS runtime/operator settings to an existing AIB.
5. Keep automatic synchronization outside KAOS core as a lightweight external sync service, potentially in a separate or AIB-adjacent repository.
6. Make the external sync service responsible for identity projection, requested-edge projection, bootstrap PermissionSet/service encoding, credentials reconciliation, status reporting, and drift detection.
7. Do not let CRD references auto-create approved grants.
8. Keep AIB as the authoritative broker for user-delegated grants, third-party sessions, token exchange, and target platform/resource grants once the AIB model supports them.
9. Do not assume public images are available until image publication is confirmed; external AIB installation must provide image repository/tag configuration as needed.
10. Keep ExtProc optional and later-stage; SDK/native calls remain the initial path from ADR-002 and ADR-009.

---

## Initial implementation implication

The initial implementation plan should likely introduce:

1. A KAOS-level AIB integration configuration, for example:

   ```text
   security.aib.enabled: true | false
   security.aib.baseURL
   security.aib.adminURL
   security.aib.adminCredentialsSecretRef
   ```

2. A KAOS CLI flag/config path such as:

   ```text
   kaos system install --aib-enabled \
     --aib-base-url ... \
     --aib-admin-url ... \
     --aib-admin-credentials-secret ...
   ```

   This should configure KAOS to use AIB, not install AIB.

3. An optional external AIB sync service that watches:

   ```text
   Agent
   MCPServer
   ModelAPI
   ```

4. Deterministic external IDs:

   ```text
   kaos://agent/<namespace>/<name>
   kaos://mcpserver/<namespace>/<name>
   kaos://modelapi/<namespace>/<name>
   ```

5. Sync service status through logs/metrics and optional Kubernetes status integration:

   ```text
   AIBSynced
   AIBRecordDrift
   AIBCredentialsReady
   AIBRequestedEdgesSynced
   AIBUnsupportedGrantModel
   ```

6. Explicit bootstrap-mode documentation if using current AIB PermissionSets to encode KAOS resource access.

7. A later migration path from bootstrap encoding to first-class AIB platform/resource grants.

---

## Host questions to answer before acceptance

1. Should the accepted decision say KAOS **never installs AIB**, and only provides CLI/runtime configuration for an externally installed AIB?
2. Should `kaos system install --aib-enabled` be the primary UX for enabling KAOS-side AIB integration?
3. Which AIB values should the KAOS CLI require: base URL, admin URL, admin credentials Secret, token-exchange audience, JWKS/issuer, runtime env vars, or SDK settings?
4. Should the synchronization service live in an AIB-adjacent repository, a standalone KAOS/AIB integration repository, or remain only as documented sample code initially?
5. Should the synchronization service be a simple Deployment with Kubernetes watch permissions, or a full Kubernetes operator with its own CRDs and status resources?
6. Should sync status be written back to KAOS resource annotations/status, or should logs/metrics be enough initially?
7. In bootstrap mode, are synthetic internal services and PermissionSets acceptable, or should KAOS wait for first-class AIB platform/resource grants?
8. Should the external sync service manage AIB agent client credential generation and rotation, or should credentials remain an external admin responsibility?
9. Should AIB admin/end-user URLs remain independently configured through AIB's Helm chart/Ingress, rather than through KAOS Gateway?
10. Should ExtProc stay out of scope until Gateway/resource-boundary enforcement is enabled later?

---

## Deferred items

- Exact KAOS CLI/config shape for enabling AIB.
- Exact external sync service implementation plan.
- Exact AIB admin authentication mechanism for KAOS sync.
- Public image coordinates and release compatibility matrix.
- Bootstrap PermissionSet naming convention.
- Migration from bootstrap encoding to first-class AIB platform/resource grants.
- Whether the external sync service should be a full Kubernetes operator or a simpler Deployment with watch permissions.
- Whether AIB should upstream a generic Kubernetes sync plugin independent of KAOS.

---

## Decision status

Proposed.

This ADR should stay in the research-question format until the host answers the deployment ownership and synchronization ownership questions. Once approved, it should be converted into the accepted ADR format used by ADR-001 through ADR-009.
