# ADR-AIB-000: AIB deployability foundation

**Status**: Accepted
**Date**: 2026-06-21

---

## Decision

Establish a deployability foundation for the Agentic Identity Broker (AIB) so that it can be built and installed into a Kubernetes cluster with no external dependencies, no published artifacts, and no secret pre-provisioning. This foundation is the base of the stacked AIB branch work that the KAOS integration depends on: [ADR-AIB-002](./ADR-AIB-002-aib-access-check-api.md) (access-check) and [ADR-AIB-001](./ADR-AIB-001-aib-python-sdk-design.md) (SDK) stack on top of it.

AIB is a private, not-yet-released project: it publishes no container images and no Helm chart releases. Anything that installs AIB must therefore build the image locally and load it into the target cluster, and the chart must come up healthy out of the box on an ephemeral backend. The foundation closes the specific gaps that block this:

1. **Public container base image.** The production, extproc, and migrate Dockerfiles default to a public `alpine:3` base (via a `BASE_IMAGE` build arg) instead of a private, non-pullable internal base, so the image builds on any machine or CI runner.

2. **Self-valid chart defaults.** The Helm chart's default values satisfy the chart's own `values.schema.json` (e.g. the `awsKms.dynamodbTimeout` field is declared), so a default `helm template`/`helm install` does not fail schema validation.

3. **Memory backend by default.** `storage.type` defaults to `memory` and `oauth2AuthorizationServer.mode` defaults to `local`. This deploys cleanly with no PostgreSQL and no migration job: AIB stores state in memory and mints actor tokens locally. The Postgres path (the Zalando `acid.zalan.do` operator) remains available but is heavier and is not required for development, CI, or the integration MVP.

4. **A committed development values preset.** `charts/agentic-identity-broker/values-dev.yaml` wires the remaining configuration an install needs to start: in-memory storage, local token issuance, plain-header pre-authentication via the `X-Remote-User` header on both the admin and end-user servers, an end-user public URL, and dev-only JWE-signing and in-memory-encryption key material. This makes `helm install -f values-dev.yaml` a single self-contained command. The preset is explicitly for ephemeral local/evaluation use only and ships clearly-labelled non-secret dev keys; it must never be used for a persistent or production install.

5. **A repeatable local image build and load path.** A `kind-image` build target produces a single-architecture image for the host architecture (substituting a stub consent UI when no web build is present, since the API and data plane do not need the real frontend) and loads it into a local KIND cluster. This is the path an `--auth-enabled` install uses while AIB has no published image.

---

## Context

The KAOS security-and-identity work integrates AIB for agent authentication and authorization. The earlier feasibility validation stood AIB up in KIND against the existing codebase and found that the deployability gaps above are not one-off setup steps but foundational AIB-side work: without them, nothing downstream (the access-check service, the gateway enforcement path, the install/sync wiring) can run.

Because AIB is unreleased, the integration cannot depend on published charts or images. The foundation therefore makes a *local build + load* workflow first-class and keeps the install free of databases and externally-provisioned secrets, so the whole path is reproducible on a developer machine and in CI.

This ADR is the base of the AIB branch stack. Keeping the foundation as its own coherent layer is also what lets the later upstream contribution land cleanly in dependency order (foundation, then access-check, then SDK) from a fork of the upstream repository.

---

## Key encoding and configuration details

### Key material wiring (chart specifics)

The chart's secret templates treat the two keys differently, which the dev preset accounts for:

- **JWE signing key** (`broker.thirdPartyOauth2.jweSigningKey`): the chart base64-encodes this value into the Secret's `data` field. The broker then expects the resulting environment value to be a base64-encoded string that it decodes to the raw key bytes. The preset therefore sets `jweSigningKey` to the **single** base64 encoding of a 32-byte value.
- **In-memory encryption key** (`broker.encryption.memory.rawKey`): the chart places this value directly into the Secret's `data` field without re-encoding, so Kubernetes decodes it once before the broker reads it. To deliver the same base64-encoded-string shape the broker expects, the preset sets `rawKey` to the **double** base64 encoding of a 32-byte value.

Both ultimately resolve to a 32-byte key inside the broker. The asymmetry is a property of the existing chart templates, documented here so the preset and any future install tooling stay correct.

### Pre-authentication

The admin and end-user servers use plain-header pre-authentication with `principalHeaderName: X-Remote-User`. AIB trusts this header only at a boundary that has already authenticated the principal (in the integration, an upstream gateway). The broker does not itself authenticate end users in this configuration; user authentication is layered in later via an external IdP.

---

## Consequences

- AIB can be built and installed by anyone with Docker and a cluster, with one chart and one values file, no database, and no manual secret creation. This unblocks the access-check service, the gateway enforcement path, and the install/sync wiring.
- The dev preset's static keys are acceptable only because the backend is ephemeral and the install is for development/evaluation. Any durable deployment must supply its own freshly-generated keys and a persistent storage backend.
- The local build-and-load workflow is a stopgap for the unreleased state of AIB. Once AIB publishes images and charts, installs can pull released artifacts instead, and this foundation is what gets contributed upstream as the first layer of the stack.
